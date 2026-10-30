"""认证路由：本地密码、LDAP、OIDC（SSO），以及当前用户信息。"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.scope import scope_tenant_id
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models import User, Tenant, DEFAULT_TENANT_ID
from app.schemas import LoginRequest, Token, MeOut
from app.services import identity
from app.services.audit import record

logger = logging.getLogger("autoops.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def _tenant_by_code(db: Session, code: str) -> Tenant:
    tenant = db.query(Tenant).filter((Tenant.code == code) | (Tenant.id == code)).first()
    if not tenant:
        tenant = db.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
    if not tenant:
        raise HTTPException(status_code=500, detail="默认租户不存在，请检查初始化")
    return tenant


def _issue(user: User, db: Session) -> Token:
    tenant = db.query(Tenant).filter(Tenant.id == (user.tenant_id or DEFAULT_TENANT_ID)).first()
    # 停用租户不允许签发令牌（超管除外），避免登录成功后才在接口层被拒
    if tenant and not tenant.enabled and not user.is_super:
        raise HTTPException(status_code=403, detail="所属租户已停用，请联系平台管理员")
    token = create_access_token(user.username, user.tenant_id, user.role)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return Token(
        access_token=token,
        username=user.username,
        role=user.role,
        tenant_id=user.tenant_id or DEFAULT_TENANT_ID,
        tenant_name=tenant.name if tenant else "",
        is_super=bool(user.is_super),
        display_name=user.display_name or user.username,
        auth_source=user.auth_source or "local",
    )


@router.get("/providers")
def providers():
    """登录页据此决定展示哪些登录方式。"""
    return identity.providers()


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    user = db.query(User).filter(User.username == payload.username).first()

    # 1) 本地密码
    if user and user.hashed_password and verify_password(payload.password, user.hashed_password):
        record(user.username, "login", "auth", detail="本地登录成功", ip=ip, tenant_id=user.tenant_id)
        return _issue(user, db)

    # 2) LDAP
    if identity.ldap_available():
        info = identity.ldap_authenticate(payload.username, payload.password)
        if info:
            user = _provision(db, info["username"], "ldap", info,
                              tenant_code=settings.LDAP_DEFAULT_TENANT,
                              role_hint=settings.LDAP_DEFAULT_ROLE)
            record(user.username, "login", "auth", detail="LDAP 登录成功", ip=ip, tenant_id=user.tenant_id)
            return _issue(user, db)

    record(payload.username, "login", "auth", detail="登录失败", ip=ip,
           tenant_id=user.tenant_id if user else DEFAULT_TENANT_ID)
    raise HTTPException(status_code=401, detail="用户名或密码错误")


def _provision(db: Session, username: str, source: str, info: dict,
               tenant_code: str = "default", role_hint: str = "operator") -> User:
    """外部身份首次登录自动开户；已存在则同步展示名/邮箱。"""
    tenant = _tenant_by_code(db, tenant_code)
    user = db.query(User).filter(User.username == username).first()
    if user:
        if info.get("email") and user.email != info["email"]:
            user.email = info["email"]
        if info.get("display_name"):
            user.display_name = info["display_name"]
        db.commit()
        return user

    user = User(
        username=username[:64],
        hashed_password="",          # 外部账号不存本地密码
        role=info.get("role") or role_hint,
        tenant_id=tenant.id,
        is_super=False,
        auth_source=source,
        email=(info.get("email") or "")[:128],
        display_name=(info.get("display_name") or username)[:64],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("外部身份自动开户: %s (%s) -> 租户 %s", username, source, tenant.code)
    return user


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant_id = scope_tenant_id(user) or user.tenant_id
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return MeOut(
        username=user.username,
        role=user.role,
        is_super=bool(user.is_super),
        display_name=user.display_name or user.username,
        email=user.email or "",
        auth_source=user.auth_source or "local",
        tenant_id=tenant_id,
        tenant_name=tenant.name if tenant else "",
        tenant_code=tenant.code if tenant else "",
        last_login_at=user.last_login_at,
    )


# ---------------------------------------------------------------- OIDC / SSO
def _sign_state(state: str) -> str:
    payload = {"state": state, "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
               "scope": "oidc-state"}
    return jose_jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _verify_state(token: str) -> str:
    try:
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("scope") != "oidc-state":
            raise ValueError("scope 不匹配")
        return payload["state"]
    except Exception:
        raise HTTPException(status_code=400, detail="SSO 状态校验失败，请重新登录")


@router.get("/oidc/login")
def oidc_login(state: str = ""):
    if not identity.oidc_available():
        raise HTTPException(status_code=400, detail="未启用 OIDC 单点登录")
    raw = state or identity.new_state()
    try:
        url = identity.build_authorize_url(_sign_state(raw))
    except Exception as e:
        logger.error("OIDC 发现文档获取失败: %s", e)
        raise HTTPException(status_code=502, detail=f"无法连接身份提供方: {e}")
    return RedirectResponse(url)


@router.get("/oidc/callback")
def oidc_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    front = settings.FRONTEND_URL.rstrip("/")
    if error:
        return RedirectResponse(f"{front}/sso/callback#error={error}")
    if not code or not state:
        return RedirectResponse(f"{front}/sso/callback#error=missing_code")
    _verify_state(state)
    try:
        claims = identity.exchange_code(code)
        mapped = identity.claims_to_user(claims)
        user = _provision(db, mapped["username"], "oidc", mapped,
                          tenant_code=mapped["tenant_code"],
                          role_hint=settings.OIDC_DEFAULT_ROLE)
        token = _issue(user, db)
        record(user.username, "login", "auth", detail="SSO 登录成功", tenant_id=user.tenant_id)
    except Exception as e:
        logger.error("OIDC 回调处理失败: %s", e)
        return RedirectResponse(f"{front}/sso/callback#error={str(e)[:120]}")
    # token 放在 fragment 里，不会出现在服务端访问日志
    return RedirectResponse(f"{front}/sso/callback#token={token.access_token}")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""
