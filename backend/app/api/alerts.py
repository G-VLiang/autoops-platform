"""告警中心：渠道配置（分级路由）、告警事件（状态机）、静默窗口。"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_write
from app.api.scope import scoped, scope_tenant_id
from app.core.database import get_db
from app.models import AlertConfig, AlertEvent, AlertSilence, User, DEFAULT_TENANT_ID
from app.schemas import (
    AlertConfigCreate, AlertConfigOut, AlertEventOut, AlertSilenceCreate, AlertSilenceOut,
)
from app.services.alert import SEVERITY_LABEL, send_alert, utcnow

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])


def _tenant_of(user: User) -> str:
    return scope_tenant_id(user) or user.tenant_id or DEFAULT_TENANT_ID


# ---------------------------------------------------------------- 渠道配置
@router.get("/configs", response_model=List[AlertConfigOut])
def list_configs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return scoped(db.query(AlertConfig), AlertConfig, user).all()


@router.post("/configs", response_model=AlertConfigOut)
def create_config(payload: AlertConfigCreate, db: Session = Depends(get_db),
                  user=Depends(require_write)):
    if payload.min_severity not in SEVERITY_LABEL:
        raise HTTPException(status_code=400, detail="min_severity 只能是 info/warning/critical")
    cfg = AlertConfig(**payload.model_dump(), tenant_id=_tenant_of(user))
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.put("/configs/{cfg_id}", response_model=AlertConfigOut)
def update_config(cfg_id: str, payload: AlertConfigCreate, db: Session = Depends(get_db),
                  user=Depends(require_write)):
    cfg = scoped(db.query(AlertConfig), AlertConfig, user).filter(
        AlertConfig.id == cfg_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    for k, v in payload.model_dump().items():
        setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.delete("/configs/{cfg_id}")
def delete_config(cfg_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    cfg = scoped(db.query(AlertConfig), AlertConfig, user).filter(
        AlertConfig.id == cfg_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    db.delete(cfg)
    db.commit()
    return {"ok": True}


@router.post("/configs/{cfg_id}/test")
def test_config(cfg_id: str, severity: str = "warning", db: Session = Depends(get_db),
                user=Depends(require_write)):
    cfg = scoped(db.query(AlertConfig), AlertConfig, user).filter(
        AlertConfig.id == cfg_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    ok = send_alert(cfg.webhook_url, cfg.channel, "告警通道测试",
                    {"来源": f"手动测试（{user.username}）",
                     "级别": SEVERITY_LABEL.get(severity, severity)},
                    severity=severity)
    return {"ok": ok, "configured": bool(cfg.webhook_url)}


# ---------------------------------------------------------------- 告警事件
@router.get("/events", response_model=List[AlertEventOut])
def list_events(status: Optional[str] = None, severity: Optional[str] = None,
                limit: int = 100, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    q = scoped(db.query(AlertEvent), AlertEvent, user)
    if status:
        q = q.filter(AlertEvent.status == status)
    if severity:
        q = q.filter(AlertEvent.severity == severity)
    return q.order_by(AlertEvent.last_seen_at.desc()).limit(min(limit, 500)).all()


@router.post("/events/{event_id}/resolve")
def resolve_event(event_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    """人工确认恢复（例如问题已在平台外解决）。"""
    ev = scoped(db.query(AlertEvent), AlertEvent, user).filter(
        AlertEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="告警不存在")
    if ev.status == "firing":
        ev.status = "resolved"
        ev.resolved_at = utcnow()
        db.commit()
    return {"ok": True, "status": ev.status}


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """看板用：活跃告警数与级别分布。"""
    base = scoped(db.query(AlertEvent), AlertEvent, user).filter(AlertEvent.status == "firing")
    rows = base.with_entities(AlertEvent.severity, func.count(AlertEvent.id)).group_by(
        AlertEvent.severity).all()
    by_sev = {sev: n for sev, n in rows}
    return {
        "active": sum(by_sev.values()),
        "by_severity": {
            "critical": by_sev.get("critical", 0),
            "warning": by_sev.get("warning", 0),
            "info": by_sev.get("info", 0),
        },
        "silenced": scoped(db.query(AlertSilence), AlertSilence, user).filter(
            AlertSilence.starts_at <= utcnow(), AlertSilence.ends_at >= utcnow()).count(),
    }


# ---------------------------------------------------------------- 静默窗口
def _silence_out(s: AlertSilence) -> AlertSilenceOut:
    now = utcnow()
    return AlertSilenceOut(
        id=s.id, name=s.name, scope=s.scope, starts_at=s.starts_at, ends_at=s.ends_at,
        reason=s.reason, created_by=s.created_by,
        active=bool(s.starts_at <= now <= s.ends_at),
    )


@router.get("/silences", response_model=List[AlertSilenceOut])
def list_silences(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = scoped(db.query(AlertSilence), AlertSilence, user).order_by(
        AlertSilence.ends_at.desc()).limit(100).all()
    return [_silence_out(s) for s in rows]


@router.post("/silences", response_model=AlertSilenceOut)
def create_silence(payload: AlertSilenceCreate, db: Session = Depends(get_db),
                   user=Depends(require_write)):
    now = utcnow()
    s = AlertSilence(
        name=payload.name or ("全局静默" if not payload.scope else "资源静默"),
        scope=payload.scope, starts_at=now, ends_at=now + timedelta(minutes=payload.minutes),
        reason=payload.reason, created_by=user.username, tenant_id=_tenant_of(user),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _silence_out(s)


@router.delete("/silences/{silence_id}")
def delete_silence(silence_id: str, db: Session = Depends(get_db),
                   user=Depends(require_write)):
    s = scoped(db.query(AlertSilence), AlertSilence, user).filter(
        AlertSilence.id == silence_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="静默窗口不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}
