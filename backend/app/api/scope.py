"""多租户查询范围。

规则：
- 普通用户只能看到自己 tenant_id 下的数据；
- 平台超管（is_super）默认跨租户可见，可通过 X-Tenant-Id 头收窄到某个租户；
- 取不到租户的脏数据（历史行）在迁移里已统一回填为 default。
"""
from typing import Optional

from fastapi import HTTPException

from app.models import DEFAULT_TENANT_ID


def scope_tenant_id(user) -> Optional[str]:
    """当前请求生效的租户；None 表示跨租户（仅超管）。"""
    if getattr(user, "is_super", False):
        return getattr(user, "_scope_tenant", None)
    return user.tenant_id or DEFAULT_TENANT_ID


def scoped(query, model, user):
    """给查询加上租户条件。model 必须有 tenant_id 列。"""
    tid = scope_tenant_id(user)
    if tid is None:
        return query
    return query.filter(model.tenant_id == tid)


def owned(obj, user):
    """单条记录是否对当前用户可见。"""
    tid = scope_tenant_id(user)
    if tid is None:
        return True
    return getattr(obj, "tenant_id", DEFAULT_TENANT_ID) == tid


def require_owned(obj, user, detail: str = "资源不存在"):
    """不可见时统一按 404 返回，避免通过 403 探测其他租户是否存在资源。"""
    if not owned(obj, user):
        raise HTTPException(status_code=404, detail=detail)
    return obj
