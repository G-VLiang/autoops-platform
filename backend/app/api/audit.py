"""审计日志：组合筛选、分页与导出（CSV）。"""
import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_admin
from app.api.scope import scoped
from app.core.database import get_db
from app.models import AuditLog, User
from app.schemas import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"],
                   dependencies=[Depends(get_current_user), Depends(require_admin)])


def _build_query(db: Session, user: User, username: Optional[str], action: Optional[str],
                 resource: Optional[str], keyword: Optional[str],
                 days: Optional[int], start: Optional[str], end: Optional[str]):
    q = scoped(db.query(AuditLog), AuditLog, user)
    if username:
        q = q.filter(AuditLog.username == username)
    if action:
        q = q.filter(AuditLog.action == action)
    if resource:
        q = q.filter(AuditLog.resource == resource)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(AuditLog.detail.like(like), AuditLog.resource_id.like(like),
                         AuditLog.username.like(like)))
    if start:
        q = q.filter(AuditLog.created_at >= _parse(start))
    if end:
        q = q.filter(AuditLog.created_at <= _parse(end))
    if days and not start:
        q = q.filter(AuditLog.created_at >= datetime.now() - timedelta(days=days))
    return q


def _parse(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.replace("Z", ""), fmt)
        except ValueError:
            continue
    raise ValueError(f"时间格式无法解析: {value}")


@router.get("")
def list_audit(page: int = 1, size: int = Query(default=50, le=200),
               username: Optional[str] = None, action: Optional[str] = None,
               resource: Optional[str] = None, keyword: Optional[str] = None,
               days: Optional[int] = None, start: Optional[str] = None,
               end: Optional[str] = None,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """分页查询审计日志；所有筛选条件可组合。"""
    try:
        q = _build_query(db, user, username, action, resource, keyword, days, start, end)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset(
        max(0, (page - 1) * size)).limit(size).all()
    return {
        "total": total, "page": page, "size": size,
        "items": [AuditOut.model_validate(r).model_dump() for r in rows],
    }


@router.get("/facets")
def facets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """筛选项候选值（用户列表 / 操作类型 / 资源类型），供前端下拉。"""
    base = scoped(db.query(AuditLog), AuditLog, user)
    users = [r[0] for r in base.with_entities(AuditLog.username).distinct().all() if r[0]]
    actions = [r[0] for r in base.with_entities(AuditLog.action).distinct().all() if r[0]]
    resources = [r[0] for r in base.with_entities(AuditLog.resource).distinct().all() if r[0]]
    return {"users": sorted(users), "actions": sorted(actions), "resources": sorted(resources)}


@router.get("/export")
def export_audit(username: Optional[str] = None, action: Optional[str] = None,
                 resource: Optional[str] = None, keyword: Optional[str] = None,
                 days: Optional[int] = None, start: Optional[str] = None,
                 end: Optional[str] = None, limit: int = Query(default=5000, le=50000),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """导出筛选结果为 CSV（UTF-8 BOM，Excel 直接打开不乱码）。"""
    q = _build_query(db, user, username, action, resource, keyword, days, start, end)
    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["时间", "用户", "操作", "资源", "资源ID", "详情", "来源IP"])
    for r in rows:
        writer.writerow([
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            r.username, r.action, r.resource, r.resource_id, r.detail, r.ip,
        ])
    data = "\ufeff" + buf.getvalue()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter([data.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.csv"'},
    )
