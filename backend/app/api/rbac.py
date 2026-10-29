"""RBAC 依赖：基于角色的权限控制。

角色：admin（全部）、operator（操作，可执行任务但不能管理凭据/用户）、viewer（只读）。
"""
from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models import User

# 各角色允许的操作集合
_ROLE_PERMISSIONS = {
    "admin": {"read", "write", "execute", "credential", "user"},
    "operator": {"read", "write", "execute"},
    "viewer": {"read"},
}


def require_permission(perm: str):
    def checker(user: User = Depends(get_current_user)) -> User:
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
