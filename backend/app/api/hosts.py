"""CMDB：主机与主机组。"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_write
from app.core.database import get_db
from app.models import Host, HostGroup
from app.schemas import HostCreate, HostOut, HostGroupCreate, HostGroupOut
from app.services.audit import record

router = APIRouter(prefix="/hosts", tags=["hosts"], dependencies=[Depends(get_current_user)])


@router.get("/groups", response_model=List[HostGroupOut])
def list_groups(db: Session = Depends(get_db)):
    groups = db.query(HostGroup).all()
    result = []
    for g in groups:
        result.append(HostGroupOut(
            id=g.id, name=g.name, description=g.description, host_count=len(g.hosts)
        ))
    return result


@router.post("/groups", response_model=HostGroupOut)
def create_group(payload: HostGroupCreate, db: Session = Depends(get_db), user=Depends(require_write)):
    if db.query(HostGroup).filter(HostGroup.name == payload.name).first():
        raise HTTPException(status_code=400, detail="主机组已存在")
    g = HostGroup(name=payload.name, description=payload.description)
    db.add(g)
    db.commit()
    db.refresh(g)
    return HostGroupOut(id=g.id, name=g.name, description=g.description, host_count=0)


@router.get("", response_model=List[HostOut])
def list_hosts(group_id: str = None, db: Session = Depends(get_db)):
    q = db.query(Host)
    if group_id:
        q = q.filter(Host.group_id == group_id)
    hosts = q.all()
    group_map = {g.id: g.name for g in db.query(HostGroup).all()}
    return [
        HostOut(
            id=h.id, hostname=h.hostname, ip=h.ip, port=h.port, os_type=h.os_type,
            os_version=h.os_version, status=h.status, tags=h.tags or [],
            group_id=h.group_id, group_name=group_map.get(h.group_id),
            created_at=h.created_at,
        ) for h in hosts
    ]


@router.post("", response_model=HostOut)
def create_host(payload: HostCreate, db: Session = Depends(get_db), user=Depends(require_write)):
    h = Host(
        hostname=payload.hostname, ip=payload.ip, port=payload.port,
        os_type=payload.os_type, os_version=payload.os_version,
        group_id=payload.group_id, tags=payload.tags or [],
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    record(user.username, "create", "host", h.id, f"添加主机 {h.hostname} ({h.ip})")
    group_map = {g.id: g.name for g in db.query(HostGroup).all()}
    return HostOut(
        id=h.id, hostname=h.hostname, ip=h.ip, port=h.port, os_type=h.os_type,
        os_version=h.os_version, status=h.status, tags=h.tags or [],
        group_id=h.group_id, group_name=group_map.get(h.group_id), created_at=h.created_at,
    )


@router.delete("/{host_id}")
def delete_host(host_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    h = db.query(Host).filter(Host.id == host_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="主机不存在")
    record(user.username, "delete", "host", host_id, f"删除主机 {h.hostname}")
    db.delete(h)
    db.commit()
    return {"ok": True}
