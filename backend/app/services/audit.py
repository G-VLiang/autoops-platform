"""审计日志记录。"""
from typing import Optional

from app.core.database import SessionLocal
from app.models import AuditLog, DEFAULT_TENANT_ID


def record(
    username: str,
    action: str,
    resource: str,
    resource_id: str = "",
    detail: str = "",
    ip: str = "",
    tenant_id: Optional[str] = DEFAULT_TENANT_ID,
):
    """独立 session 写入审计日志，不干扰业务事务。"""
    db = SessionLocal()
    try:
        db.add(AuditLog(
            username=username, action=action, resource=resource,
            resource_id=resource_id, detail=detail[:512], ip=ip,
            tenant_id=tenant_id or DEFAULT_TENANT_ID,
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
