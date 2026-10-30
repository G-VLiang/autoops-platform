"""租户管理（平台超管）。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_super
from app.core.database import get_db
from app.models import Tenant, User, Host
from app.schemas import TenantCreate, TenantOut
from app.services.audit import record

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=List[TenantOut])
def list_tenants(db: Session = Depends(get_db), user: User = Depends(require_super)):
    user_counts = dict(db.query(User.tenant_id, func.count()).group_by(User.tenant_id).all())
    host_counts = dict(db.query(Host.tenant_id, func.count()).group_by(Host.tenant_id).all())
    tenants = db.query(Tenant).order_by(Tenant.created_at.asc()).all()
    return [
        TenantOut(
            id=t.id, code=t.code, name=t.name, description=t.description or "",
            enabled=bool(t.enabled), created_at=t.created_at,
            user_count=int(user_counts.get(t.id, 0)),
            host_count=int(host_counts.get(t.id, 0)),
        ) for t in tenants
    ]


@router.post("", response_model=TenantOut)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_super)):
    if db.query(Tenant).filter((Tenant.code == payload.code) | (Tenant.name == payload.name)).first():
        raise HTTPException(status_code=400, detail="租户编码或名称已存在")
    tenant = Tenant(code=payload.code, name=payload.name,
                    description=payload.description, enabled=payload.enabled)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    record(user.username, "create", "tenant", tenant.id, f"创建租户 {tenant.code}",
           tenant_id=tenant.id)
    return TenantOut(id=tenant.id, code=tenant.code, name=tenant.name,
                     description=tenant.description or "", enabled=bool(tenant.enabled),
                     created_at=tenant.created_at, user_count=0, host_count=0)


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: str, payload: TenantCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_super)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    if tenant.id == "default" and not payload.enabled:
        raise HTTPException(status_code=400, detail="默认租户不可停用")
    tenant.name = payload.name
    tenant.description = payload.description
    tenant.enabled = payload.enabled
    db.commit()
    db.refresh(tenant)
    record(user.username, "update", "tenant", tenant.id,
           f"更新租户 {tenant.code} enabled={tenant.enabled}", tenant_id=tenant.id)
    return TenantOut(id=tenant.id, code=tenant.code, name=tenant.name,
                     description=tenant.description or "", enabled=bool(tenant.enabled),
                     created_at=tenant.created_at)


@router.get("/current")
def current_tenant(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    return {"id": tenant.id, "code": tenant.code, "name": tenant.name,
            "enabled": bool(tenant.enabled)}
