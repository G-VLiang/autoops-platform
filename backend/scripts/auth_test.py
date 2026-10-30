"""认证源测试：LDAP 回退开户、OIDC 回调开户、角色映射、停用租户拦截。

无真实 LDAP / IdP 时，对 identity 层打桩，验证「协议无关」的业务链路完整。
    ./venv/Scripts/python.exe scripts/auth_test.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

TMP = Path(tempfile.mkdtemp(prefix="autoops_auth_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'auth.db'}"
os.environ["ARTIFACT_DIR"] = str(TMP / "artifacts")
os.environ["SCHEDULER_ENABLED"] = "false"      # 本测试不关心调度
os.environ["SECRET_KEY"] = "auth-test-secret-key"
os.environ["LDAP_ENABLED"] = "true"            # 打开开关，具体协议层会被打桩
os.environ["LDAP_DEFAULT_ROLE"] = "operator"
os.environ["LDAP_DEFAULT_TENANT"] = "default"
os.environ["OIDC_ENABLED"] = "true"
os.environ["OIDC_ISSUER"] = "https://idp.example.com"
os.environ["OIDC_CLIENT_ID"] = "autoops"
os.environ["OIDC_DEFAULT_ROLE"] = "viewer"
os.environ["OIDC_ROLE_MAP"] = "ops-team:operator,platform-admins:admin"
os.environ["FRONTEND_URL"] = "http://localhost:5173"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import User, Tenant  # noqa: E402
from app.services import identity  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, extra=""):
    if cond:
        PASSED.append(name)
        print(f"  [OK] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {extra}")


def main():
    with TestClient(app) as c:
        print("\n== 1. 角色映射（纯函数） ==")
        check("组全匹配 -> admin",
              identity.map_role({"groups": ["platform-admins"]}, "platform-admins:admin", "operator") == "admin")
        check("单字符串声明也能匹配",
              identity.map_role({"role": "ops-team"}, "ops-team:operator", "viewer") == "operator")
        check("未命中回落到默认角色",
              identity.map_role({"groups": ["other"]}, "ops-team:operator", "viewer") == "viewer")
        check("未配置映射时用默认角色",
              identity.map_role({"groups": ["x"]}, "", "operator") == "operator")

        claims = identity.claims_to_user({
            "preferred_username": "zhangsan", "email": "zs@corp.com",
            "name": "张三", "groups": ["ops-team"], "tenant": "acme",
        })
        check("claims 映射用户名", claims["username"] == "zhangsan", claims)
        check("claims 映射邮箱/显示名", claims["email"] == "zs@corp.com" and claims["display_name"] == "张三")
        check("claims 映射角色", claims["role"] == "operator", claims)

        print("\n== 2. LDAP 登录（打桩协议层） ==")
        with patch.object(identity, "ldap_available", return_value=True), \
             patch.object(identity, "ldap_authenticate",
                          return_value={"username": "ldap-user", "email": "ldap@corp.com",
                                        "display_name": "LDAP 用户"}):
            r = c.post("/api/v1/auth/login", json={"username": "ldap-user", "password": "any"})
        check("LDAP 用户首次登录成功", r.status_code == 200, r.text)
        body = r.json()
        check("自动开户角色 = LDAP_DEFAULT_ROLE", body.get("role") == "operator", body)
        check("自动开户租户 = default", body.get("tenant_id") == "default", body)
        check("auth_source = ldap", body.get("auth_source") == "ldap", body)

        db = SessionLocal()
        try:
            u = db.query(User).filter(User.username == "ldap-user").first()
            check("外部账号不落本地密码", (u.hashed_password or "") == "", u.hashed_password)
        finally:
            db.close()

        with patch.object(identity, "ldap_available", return_value=True), \
             patch.object(identity, "ldap_authenticate", return_value=None):
            r = c.post("/api/v1/auth/login", json={"username": "ldap-user", "password": "bad"})
        check("LDAP 密码错误被拒", r.status_code == 401, r.status_code)

        print("\n== 3. OIDC 回调（打桩令牌交换） ==")
        state = identity._sign_state if hasattr(identity, "_sign_state") else None  # noqa: F841
        from app.api.auth import _sign_state
        signed = _sign_state("nonce-123")
        with patch.object(identity, "exchange_code", return_value={
            "preferred_username": "sso-user", "email": "sso@corp.com",
            "name": "SSO 用户", "groups": ["ops-team"],
        }):
            r = c.get(f"/api/v1/auth/oidc/callback?code=abc&state={signed}",
                      follow_redirects=False)
        check("回调重定向到前端", r.status_code in (302, 307), r.status_code)
        loc = r.headers.get("location", "")
        check("token 放在 fragment（不进服务端日志）", "#token=" in loc, loc[:120])

        token = loc.split("#token=")[-1] if "#token=" in loc else ""
        if token:
            me = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            check("SSO 令牌可用", me.status_code == 200, me.status_code)
            check("SSO 用户角色按组映射", me.json().get("role") == "operator", me.json())

        bad = c.get("/api/v1/auth/oidc/callback?code=abc&state=forged", follow_redirects=False)
        check("伪造 state 被拒", bad.status_code in (302, 400), bad.status_code)

        print("\n== 4. 停用租户拦截 ==")
        db = SessionLocal()
        try:
            db.add(Tenant(id="frozen", code="frozen", name="停用租户", enabled=False))
            from app.core.security import hash_password
            db.add(User(username="frozen-user", hashed_password=hash_password("pass1234"),
                        role="admin", tenant_id="frozen"))
            db.commit()
        finally:
            db.close()
        r = c.post("/api/v1/auth/login", json={"username": "frozen-user", "password": "pass1234"})
        check("停用租户用户登录被拒", r.status_code == 403, r.status_code)

    print(f"\n{'='*52}")
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("失败项：", ", ".join(FAILED))
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
