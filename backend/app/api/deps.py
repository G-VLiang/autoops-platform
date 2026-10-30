"""认证依赖：解析 JWT、校验租户、注入当前请求的租户范围。"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User, Tenant, DEFAULT_TENANT_ID

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("未登录")
    payload = decode_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise _unauthorized("令牌无效或已过期")

    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user:
        raise _unauthorized("用户不存在")

    # 令牌里的租户必须与账号当前租户一致，避免改租户后旧令牌继续生效
    token_tid = payload.get("tid")
    if token_tid and token_tid != (user.tenant_id or DEFAULT_TENANT_ID):
        raise _unauthorized("令牌所属租户已变更，请重新登录")

    tenant_id = user.tenant_id or DEFAULT_TENANT_ID
    if not user.is_super:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and not tenant.enabled:
            raise HTTPException(status_code=403, detail="所属租户已停用")

    # 平台超管可用 X-Tenant-Id 收窄到单个租户视角
    requested = (request.headers.get("x-tenant-id") or "").strip()
    if requested and user.is_super:
        exists = db.query(Tenant).filter(
            (Tenant.id == requested) | (Tenant.code == requested)
        ).first()
        user._scope_tenant = exists.id if exists else None
    else:
        user._scope_tenant = None
    return user


def get_current_username(user: User = Depends(get_current_user)) -> str:
    return user.username
