"""RBAC 依赖：基于角色的权限控制。

角色：superadmin（平台超管，跨租户）、admin（租户管理员）、operator（可执行）、viewer（只读）。
"""
from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models import User

# 各角色允许的操作集合
_ROLE_PERMISSIONS = {
    "superadmin": {"read", "write", "execute", "credential", "user", "tenant"},
    "admin": {"read", "write", "execute", "credential", "user"},
    "operator": {"read", "write", "execute"},
    "viewer": {"read"},
}

VALID_ROLES = tuple(_ROLE_PERMISSIONS.keys())


def require_permission(perm: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        # 平台超管永远放行（其 is_super 标记与角色双保险）
        if user.is_super:
            return user
        allowed = _ROLE_PERMISSIONS.get(user.role, {"read"})
        if perm not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行此操作")
        return user
    return checker


def require_write(user: User = Depends(get_current_user)) -> User:
    return require_permission("write")(user)


def require_execute(user: User = Depends(get_current_user)) -> User:
    return require_permission("execute")(user)


def require_admin(user: User = Depends(get_current_user)) -> User:
    return require_permission("credential")(user)


def require_super(user: User = Depends(get_current_user)) -> User:
    if not user.is_super:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要平台管理员权限")
    return user
