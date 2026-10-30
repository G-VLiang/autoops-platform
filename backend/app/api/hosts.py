"""CMDB：主机与主机组，含连通性探测。"""
import logging
import time
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_write
from app.api.scope import scoped, require_owned, scope_tenant_id
from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.models import Host, HostGroup, User, DEFAULT_TENANT_ID
from app.schemas import (
    HostCreate, HostOut, HostGroupCreate, HostGroupOut,
    ProbeRequest, ProbeItem, ProbeSummary,
)
from app.services import probe
from app.services.audit import record

logger = logging.getLogger("autoops.hosts")
router = APIRouter(prefix="/hosts", tags=["hosts"], dependencies=[Depends(get_current_user)])


def _tenant_of(user: User) -> str:
    return scope_tenant_id(user) or user.tenant_id or DEFAULT_TENANT_ID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/groups", response_model=List[HostGroupOut])
def list_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    groups = scoped(db.query(HostGroup), HostGroup, user).all()
    return [
        HostGroupOut(id=g.id, name=g.name, description=g.description, host_count=len(g.hosts))
        for g in groups
    ]


@router.post("/groups", response_model=HostGroupOut)
def create_group(payload: HostGroupCreate, db: Session = Depends(get_db),
                 user=Depends(require_write)):
    tenant_id = _tenant_of(user)
    exists = scoped(db.query(HostGroup), HostGroup, user).filter(
        HostGroup.name == payload.name).first()
    if exists:
        raise HTTPException(status_code=400, detail="主机组已存在")
    g = HostGroup(name=payload.name, description=payload.description, tenant_id=tenant_id)
    db.add(g)
    db.commit()
    db.refresh(g)
    return HostGroupOut(id=g.id, name=g.name, description=g.description, host_count=0)


@router.get("", response_model=List[HostOut])
def list_hosts(group_id: str = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    q = scoped(db.query(Host), Host, user)
    if group_id:
        q = q.filter(Host.group_id == group_id)
    hosts = q.all()
    group_map = {g.id: g.name for g in scoped(db.query(HostGroup), HostGroup, user).all()}
    return [
        HostOut(
            id=h.id, hostname=h.hostname, ip=h.ip, port=h.port, os_type=h.os_type,
            os_version=h.os_version, status=h.status, tags=h.tags or [],
            group_id=h.group_id, group_name=group_map.get(h.group_id),
            last_seen=h.last_seen, probe_at=h.probe_at,
            probe_latency_ms=h.probe_latency_ms, probe_message=h.probe_message or "",
            created_at=h.created_at,
        ) for h in hosts
    ]


# ---- 连通性探测 ----
def _apply_probe(host: Host, result: dict) -> None:
    now = _utcnow()
    host.status = "online" if result["online"] else "offline"
    host.probe_at = now
    host.probe_latency_ms = result.get("latency_ms")
    host.probe_message = (result.get("message") or "")[:255]
    if result["online"]:
        host.last_seen = now


@router.post("/probe", response_model=ProbeSummary)
def probe_hosts(payload: ProbeRequest, db: Session = Depends(get_db),
                user=Depends(require_write)):
    """立即探测：不传 host_ids 则探测当前租户全部主机。"""
    q = scoped(db.query(Host), Host, user)
    if payload.host_ids:
        q = q.filter(Host.id.in_(payload.host_ids))
    hosts = q.all()
    if not hosts:
        return ProbeSummary(total=0, online=0, offline=0, elapsed_ms=0, results=[])

    started = time.monotonic()
    payload_hosts = [{"id": h.id, "hostname": h.hostname, "ip": h.ip, "port": h.port}
                     for h in hosts]
    results = probe.probe_many(
        payload_hosts, method=settings.PROBE_METHOD, port=payload.port,
        timeout=settings.PROBE_TIMEOUT_SECONDS, workers=settings.PROBE_WORKERS,
    )
    by_id = {r["host_id"]: r for r in results}
    online = 0
    for h in hosts:
        r = by_id.get(h.id)
        if r:
            _apply_probe(h, r)
            online += 1 if r["online"] else 0
    db.commit()

    elapsed = int((time.monotonic() - started) * 1000)
    record(user.username, "update", "host", "", f"探测 {len(hosts)} 台主机，在线 {online} 台",
           tenant_id=_tenant_of(user))
    return ProbeSummary(
        total=len(hosts), online=online, offline=len(hosts) - online, elapsed_ms=elapsed,
        results=[ProbeItem(**r) for r in results],
    )


@router.post("/{host_id}/probe", response_model=ProbeItem)
def probe_single(host_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    h = scoped(db.query(Host), Host, user).filter(Host.id == host_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="主机不存在")
    r = probe.probe_one({"id": h.id, "hostname": h.hostname, "ip": h.ip, "port": h.port},
                        method=settings.PROBE_METHOD, timeout=settings.PROBE_TIMEOUT_SECONDS)
    _apply_probe(h, r)
    db.commit()
    return ProbeItem(**r)


def probe_all_job() -> None:
    """定时任务入口（由调度器 leader 调用）：刷新全部租户主机状态。"""
    db = SessionLocal()
    try:
        hosts = db.query(Host).all()
        if not hosts:
            return
        payload_hosts = [{"id": h.id, "hostname": h.hostname, "ip": h.ip, "port": h.port}
                         for h in hosts]
        results = probe.probe_many(
            payload_hosts, method=settings.PROBE_METHOD,
            timeout=settings.PROBE_TIMEOUT_SECONDS, workers=settings.PROBE_WORKERS,
        )
        by_id = {r["host_id"]: r for r in results}
        online = 0
        for h in hosts:
            r = by_id.get(h.id)
            if r:
                _apply_probe(h, r)
                online += 1 if r["online"] else 0
        db.commit()
        logger.info("[探活] 共 %s 台，在线 %s 台", len(hosts), online)
    except Exception as e:
        db.rollback()
        logger.warning("[探活] 执行失败: %s", e)
    finally:
        db.close()


@router.post("", response_model=HostOut)
def create_host(payload: HostCreate, db: Session = Depends(get_db), user=Depends(require_write)):
    # 目标组必须属于当前租户，避免越权挂载
    if payload.group_id:
        group = scoped(db.query(HostGroup), HostGroup, user).filter(
            HostGroup.id == payload.group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="主机组不存在")
    h = Host(
        hostname=payload.hostname, ip=payload.ip, port=payload.port,
        os_type=payload.os_type, os_version=payload.os_version,
        group_id=payload.group_id, tags=payload.tags or [],
        tenant_id=_tenant_of(user),
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    record(user.username, "create", "host", h.id, f"添加主机 {h.hostname} ({h.ip})",
           tenant_id=h.tenant_id)
    group_map = {g.id: g.name for g in scoped(db.query(HostGroup), HostGroup, user).all()}
    return HostOut(
        id=h.id, hostname=h.hostname, ip=h.ip, port=h.port, os_type=h.os_type,
        os_version=h.os_version, status=h.status, tags=h.tags or [],
        group_id=h.group_id, group_name=group_map.get(h.group_id), created_at=h.created_at,
    )


@router.delete("/{host_id}")
def delete_host(host_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    h = scoped(db.query(Host), Host, user).filter(Host.id == host_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="主机不存在")
    record(user.username, "delete", "host", host_id, f"删除主机 {h.hostname}", tenant_id=h.tenant_id)
    db.delete(h)
    db.commit()
    return {"ok": True}
