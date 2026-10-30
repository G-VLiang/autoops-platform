"""统计与趋势：看板所需的聚合数据（全部在 SQL 侧聚合，不把明细拉到应用层）。"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.scope import scope_tenant_id
from app.core.database import get_db
from app.models import (
    Host, HostGroup, Task, TaskLog, InspectionPlan, InspectionReport,
    InspectionTemplate, AlertConfig, Tenant, User, Credential,
)

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(get_current_user)])

TASK_STATUSES = ("success", "partial", "failed", "running", "pending")
REPORT_STATUSES = ("success", "partial", "failed")


def _tid(user: User) -> Optional[str]:
    """None = 平台超管跨租户统计。"""
    return scope_tenant_id(user)


def _filter(q, model, user):
    tid = _tid(user)
    return q if tid is None else q.filter(model.tenant_id == tid)


def _counts_by_status(db: Session, model, user) -> Dict[str, int]:
    q = _filter(db.query(model.status, func.count()), model, user).group_by(model.status)
    return {str(s or "unknown"): int(c) for s, c in q.all()}


def _since(days: int) -> datetime:
    start = datetime.utcnow() - timedelta(days=max(days - 1, 0))
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _daily_series(db: Session, model, user, days: int) -> Dict[str, Dict[str, int]]:
    day = func.date(model.created_at)
    q = _filter(
        db.query(day.label("d"), model.status, func.count()), model, user,
    ).filter(model.created_at >= _since(days)).group_by(day, model.status)
    out: Dict[str, Dict[str, int]] = {}
    for d, status, cnt in q.all():
        out.setdefault(str(d)[:10], {})[str(status or "unknown")] = int(cnt)
    return out


def _date_keys(days: int) -> List[str]:
    today = datetime.utcnow().date()
    return [(today - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]


# ---------------------------------------------------------------- 内部实现
def build_overview(db: Session, user: User) -> dict:
    host_status = _counts_by_status(db, Host, user)
    task_status = _counts_by_status(db, Task, user)
    report_status = _counts_by_status(db, InspectionReport, user)

    total_hosts = sum(host_status.values())
    online = host_status.get("online", 0)
    done = (task_status.get("success", 0) + task_status.get("partial", 0)
            + task_status.get("failed", 0))

    since7 = datetime.utcnow() - timedelta(days=7)
    q7 = _filter(db.query(InspectionReport.status, func.count()), InspectionReport, user).filter(
        InspectionReport.created_at >= since7).group_by(InspectionReport.status)
    r7 = {str(s): int(c) for s, c in q7.all()}
    r7_total = sum(r7.values())

    plans_total = _filter(db.query(func.count(InspectionPlan.id)), InspectionPlan, user).scalar() or 0
    plans_enabled = _filter(db.query(func.count(InspectionPlan.id)), InspectionPlan, user).filter(
        InspectionPlan.enabled == True).scalar() or 0  # noqa: E712
    templates_total = _filter(
        db.query(func.count(InspectionTemplate.id)), InspectionTemplate, user).scalar() or 0
    alerts_total = _filter(db.query(func.count(AlertConfig.id)), AlertConfig, user).filter(
        AlertConfig.enabled == True).scalar() or 0  # noqa: E712
    credentials_total = _filter(
        db.query(func.count(Credential.id)), Credential, user).scalar() or 0
    groups_total = _filter(db.query(func.count(HostGroup.id)), HostGroup, user).scalar() or 0

    data = {
        "hosts": {
            "total": total_hosts,
            "online": online,
            "offline": host_status.get("offline", 0),
            "unknown": host_status.get("unknown", 0),
            "online_rate": round(online / total_hosts * 100, 1) if total_hosts else 0.0,
        },
        "tasks": {
            "total": sum(task_status.values()),
            "by_status": {s: task_status.get(s, 0) for s in TASK_STATUSES},
            "success_rate": round(task_status.get("success", 0) / done * 100, 1) if done else 0.0,
        },
        "reports": {
            "total": sum(report_status.values()),
            "by_status": {s: report_status.get(s, 0) for s in REPORT_STATUSES},
            "health_7d": round(r7.get("success", 0) / r7_total * 100, 1) if r7_total else None,
        },
        "catalog": {
            "groups": int(groups_total),
            "templates": int(templates_total),
            "plans": int(plans_total),
            "plans_enabled": int(plans_enabled),
            "alerts": int(alerts_total),
            "credentials": int(credentials_total),
        },
    }
    if user.is_super:
        data["tenants_total"] = int(db.query(func.count(Tenant.id)).scalar() or 0)
    return data


def build_trend(db: Session, user: User, days: int) -> dict:
    task_map = _daily_series(db, Task, user, days)
    report_map = _daily_series(db, InspectionReport, user, days)
    points = []
    for key in _date_keys(days):
        t = task_map.get(key, {})
        r = report_map.get(key, {})
        t_total = sum(t.values())
        r_total = sum(r.values())
        points.append({
            "date": key,
            "tasks": {
                "total": t_total,
                "success": t.get("success", 0),
                "partial": t.get("partial", 0),
                "failed": t.get("failed", 0),
            },
            "reports": {
                "total": r_total,
                "success": r.get("success", 0),
                "partial": r.get("partial", 0),
                "failed": r.get("failed", 0),
            },
            "task_success_rate": round(t.get("success", 0) / t_total * 100, 1) if t_total else None,
            "report_health": round(r.get("success", 0) / r_total * 100, 1) if r_total else None,
        })
    return {"days": days, "points": points}


def build_hotspots(db: Session, user: User, days: int = 30, limit: int = 5) -> dict:
    since = datetime.utcnow() - timedelta(days=days)

    # 失败/不可达最多的主机：join 任务表以同时应用租户过滤
    fq = db.query(TaskLog.host, func.count().label("cnt")).join(
        Task, TaskLog.task_id == Task.id
    ).filter(TaskLog.event.in_(("failed", "unreachable")), Task.created_at >= since)
    fq = _filter(fq, Task, user).group_by(TaskLog.host).order_by(func.count().desc()).limit(limit)
    failed_hosts = [{"host": h or "-", "count": int(c)} for h, c in fq.all()]

    # 巡检模板失败率（窗口内执行过的模板）
    tq = db.query(
        InspectionReport.template_name,
        func.count().label("total"),
        func.sum(case((InspectionReport.status == "success", 1), else_=0)).label("ok"),
    ).filter(InspectionReport.created_at >= since, InspectionReport.template_name != "")
    tq = _filter(tq, InspectionReport, user).group_by(InspectionReport.template_name).limit(limit * 4)
    failing_templates = []
    for name, total, ok in tq.all():
        total, ok = int(total or 0), int(ok or 0)
        if total <= 0:
            continue
        failing_templates.append({
            "template": name, "total": total, "ok": ok,
            "fail_rate": round((total - ok) / total * 100, 1),
        })
    failing_templates.sort(key=lambda x: (-x["fail_rate"], -x["total"]))
    failing_templates = failing_templates[:limit]

    cq = db.query(InspectionTemplate.category, func.count()).group_by(InspectionTemplate.category)
    categories = [{"name": str(c or "custom"), "value": int(n)}
                  for c, n in _filter(cq, InspectionTemplate, user).all()]

    ttq = db.query(Task.task_type, func.count()).group_by(Task.task_type)
    task_types = [{"name": str(t or "adhoc"), "value": int(n)}
                  for t, n in _filter(ttq, Task, user).all()]

    return {
        "days": days,
        "failed_hosts": failed_hosts,
        "failing_templates": failing_templates,
        "categories": categories,
        "task_types": task_types,
    }


# ---------------------------------------------------------------- 路由
@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return build_overview(db, user)


@router.get("/trend")
def trend(days: int = Query(14, ge=3, le=90), db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    return build_trend(db, user, days)


@router.get("/hotspots")
def hotspots(days: int = Query(30, ge=1, le=180), limit: int = Query(5, ge=1, le=20),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return build_hotspots(db, user, days, limit)


@router.get("/dashboard")
def dashboard(days: int = Query(14, ge=3, le=90), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """看板一次性取数，减少前端请求数。"""
    return {
        "overview": build_overview(db, user),
        "trend": build_trend(db, user, days),
        "hotspots": build_hotspots(db, user),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
