"""可插拔身份源：LDAP / OIDC（SSO）。

设计原则：
- 默认全部关闭，关闭时零依赖、零开销（ldap3 延迟导入）；
- 与本地账号并存：本地密码优先，失败后再尝试 LDAP；
- 外部账号首次登录自动开户（角色/租户由配置决定），后续以本地记录为准。
"""
from __future__ import annotations

import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("autoops.identity")

# 关闭代理：内网 IdP / 代理环境不一致时容易踩坑，行为可控
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_discovery_cache: Dict[str, dict] = {}


# ---------------------------------------------------------------- LDAP
def ldap_available() -> bool:
    if not settings.LDAP_ENABLED:
        return False
    try:
        import ldap3  # noqa: F401
        return True
    except ImportError:
        logger.warning("LDAP_ENABLED=true 但未安装 ldap3（pip install ldap3）")
        return False


def ldap_authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """校验 LDAP 账号密码。成功返回用户信息，失败返回 None。"""
    if not ldap_available() or not password:
        return None
    try:
        from ldap3 import Server, Connection, NONE, ALL
        from ldap3.utils.conv import escape_filter_chars
    except ImportError:
        return None

    server_url = settings.LDAP_SERVER
    if not server_url:
        logger.warning("LDAP_SERVER 未配置")
        return None

    use_ssl = settings.LDAP_USE_SSL or server_url.lower().startswith("ldaps://")
    try:
        server = Server(server_url, use_ssl=use_ssl, get_info=NONE, connect_timeout=settings.LDAP_TIMEOUT)
    except Exception as e:
        logger.error("LDAP 服务器地址无效: %s", e)
        return None

    info: Dict[str, Any] = {"username": username, "email": "", "display_name": username}

    try:
        # 方式 A：直接用户 DN 模板绑定（AD 常见 CN=xxx,OU=...,DC=...）
        if settings.LDAP_USER_DN_TEMPLATE:
            user_dn = settings.LDAP_USER_DN_TEMPLATE.format(username=escape_filter_chars(username))
            conn = Connection(server, user=user_dn, password=password,
                              authentication="SIMPLE", receive_timeout=settings.LDAP_TIMEOUT)
            if not conn.bind():
                return None
            # 已绑定，读自己的属性
            conn.search(user_dn, "(objectClass=*)",
                        attributes=[settings.LDAP_ATTR_MAIL, settings.LDAP_ATTR_DISPLAY])
            _fill_from_entry(conn, info)
            conn.unbind()
            return info

        # 方式 B：服务账号搜索 DN，再用用户 DN 重新绑定校验密码
        bind_user = settings.LDAP_BIND_DN or None
        bind_pwd = settings.LDAP_BIND_PASSWORD or None
        base_conn = Connection(server, user=bind_user, password=bind_pwd,
                               authentication="SIMPLE" if bind_user else "ANONYMOUS",
                               receive_timeout=settings.LDAP_TIMEOUT)
        if not base_conn.bind():
            logger.error("LDAP 服务账号绑定失败: %s", base_conn.result)
            return None

        flt = settings.LDAP_USER_FILTER.format(username=escape_filter_chars(username))
        base_conn.search(settings.LDAP_BASE_DN, flt,
                         attributes=[settings.LDAP_ATTR_MAIL, settings.LDAP_ATTR_DISPLAY])
        if not base_conn.entries:
            base_conn.unbind()
            return None
        entry = base_conn.entries[0]
        user_dn = entry.entry_dn
        _fill_from_values(entry, info, settings)
        base_conn.unbind()

        user_conn = Connection(server, user=user_dn, password=password,
                               authentication="SIMPLE", receive_timeout=settings.LDAP_TIMEOUT)
        ok = user_conn.bind()
        user_conn.unbind()
        return info if ok else None
    except Exception as e:
        logger.error("LDAP 认证异常: %s", e)
        return None


def _fill_from_entry(conn, info: Dict[str, Any]):
    try:
        entry = conn.response[0]["attributes"] if conn.response else {}
        if isinstance(entry.get(settings.LDAP_ATTR_MAIL), list):
            info["email"] = (entry.get(settings.LDAP_ATTR_MAIL) or [""])[0]
        else:
            info["email"] = entry.get(settings.LDAP_ATTR_MAIL) or ""
        disp = entry.get(settings.LDAP_ATTR_DISPLAY)
        info["display_name"] = (disp[0] if isinstance(disp, list) and disp else disp) or info["username"]
    except Exception:
        pass


def _fill_from_values(entry, info: Dict[str, Any], cfg):
    try:
        mail = entry[cfg.LDAP_ATTR_MAIL].value if cfg.LDAP_ATTR_MAIL in entry else ""
        disp = entry[cfg.LDAP_ATTR_DISPLAY].value if cfg.LDAP_ATTR_DISPLAY in entry else ""
        info["email"] = str(mail or "")
        info["display_name"] = str(disp or info["username"])
    except Exception:
        pass


# ---------------------------------------------------------------- OIDC
def oidc_available() -> bool:
    return bool(settings.OIDC_ENABLED and settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID)


def _discover() -> dict:
    issuer = settings.OIDC_ISSUER.rstrip("/")
    if issuer in _discovery_cache:
        return _discovery_cache[issuer]
    url = issuer + "/.well-known/openid-configuration"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with _OPENER.open(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    _discovery_cache[issuer] = data
    return data


def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_authorize_url(state: str) -> str:
    cfg = _discover()
    params = {
        "client_id": settings.OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": settings.OIDC_SCOPES,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "state": state,
    }
    sep = "&" if "?" in cfg["authorization_endpoint"] else "?"
    return cfg["authorization_endpoint"] + sep + urllib.parse.urlencode(params)


def exchange_code(code: str) -> Dict[str, Any]:
    """用授权码换取令牌，并返回已校验的 claims。"""
    cfg = _discover()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        cfg["token_endpoint"], data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    with _OPENER.open(req, timeout=20) as r:
        tokens = json.loads(r.read().decode())

    claims: Dict[str, Any] = {}
    id_token = tokens.get("id_token")
    if id_token:
        claims = _verify_id_token(id_token, cfg)
    if not claims and tokens.get("access_token") and cfg.get("userinfo_endpoint"):
        req2 = urllib.request.Request(
            cfg["userinfo_endpoint"],
            headers={"Authorization": "Bearer " + tokens["access_token"], "Accept": "application/json"},
        )
        with _OPENER.open(req2, timeout=20) as r:
            claims = json.loads(r.read().decode())
    return claims


def _verify_id_token(id_token: str, cfg: dict) -> Dict[str, Any]:
    from jose import jwt as jose_jwt
    from jose import jwk as jose_jwk

    jwks_uri = cfg.get("jwks_uri")
    header = jose_jwt.get_unverified_header(id_token)
    key = None
    if jwks_uri:
        req = urllib.request.Request(jwks_uri, headers={"Accept": "application/json"})
        with _OPENER.open(req, timeout=15) as r:
            jwks = json.loads(r.read().decode())
        for k in jwks.get("keys", []):
            if not header.get("kid") or k.get("kid") == header.get("kid"):
                key = jose_jwk.construct(k).public_key()
                break
    if key is None:
        raise ValueError("无法从 JWKS 解析签名公钥")

    return jose_jwt.decode(
        id_token, key,
        algorithms=[header.get("alg", "RS256")],
        audience=settings.OIDC_CLIENT_ID,
        issuer=settings.OIDC_ISSUER.rstrip("/"),
        options={"verify_at_hash": False},
    )


def claims_to_user(claims: Dict[str, Any]) -> Dict[str, Any]:
    """把 IdP claims 映射成平台用户字段。"""
    username = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
        or "sso-user"
    )
    tenant = settings.OIDC_DEFAULT_TENANT
    claim_key = settings.OIDC_DEFAULT_TENANT_FROM_CLAIM
    if claim_key and claims.get(claim_key):
        tenant = str(claims[claim_key])

    return {
        "username": str(username)[:64],
        "email": str(claims.get("email") or "")[:128],
        "display_name": str(claims.get("name") or username)[:64],
        "role": map_role(claims, settings.OIDC_ROLE_MAP, settings.OIDC_DEFAULT_ROLE),
        "tenant_code": tenant,
    }


def map_role(claims: Dict[str, Any], role_map_text: str, default_role: str) -> str:
    """按 IdP 组/角色映射平台角色，未命中则用默认角色。"""
    if not role_map_text:
        return default_role
    groups = set()
    for key in ("groups", "roles", "group", "role", "wids"):
        val = claims.get(key)
        if isinstance(val, str):
            groups.add(val)
        elif isinstance(val, list):
            groups.update(str(v) for v in val)
    for pair in role_map_text.split(","):
        if ":" not in pair:
            continue
        idp_value, platform_role = pair.split(":", 1)
        if idp_value.strip() in groups:
            return platform_role.strip()
    return default_role


def providers() -> Dict[str, Any]:
    return {
        "local": True,
        "ldap": ldap_available(),
        "oidc": oidc_available(),
        "oidc_start": "/api/v1/auth/oidc/login",
    }
