"""凭据管理 + 审计日志。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_admin
from app.api.scope import scoped, scope_tenant_id
from app.core.database import get_db
from app.core.crypto import encrypt
from app.models import Credential, User, DEFAULT_TENANT_ID
from app.schemas import CredentialCreate, CredentialOut
from app.services.audit import record

router = APIRouter(tags=["credentials"], dependencies=[Depends(get_current_user)])


# ---- 凭据 ----
@router.get("/credentials", response_model=List[CredentialOut], dependencies=[Depends(require_admin)])
def list_credentials(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return scoped(db.query(Credential), Credential, user).all()


@router.post("/credentials", response_model=CredentialOut, dependencies=[Depends(require_admin)])
def create_credential(payload: CredentialCreate, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    if not payload.secret:
        raise HTTPException(status_code=400, detail="secret 不能为空")
    cred = Credential(
        name=payload.name, type=payload.type, username=payload.username,
        secret_encrypted=encrypt(payload.secret),
        tenant_id=scope_tenant_id(user) or user.tenant_id or DEFAULT_TENANT_ID,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    record(user.username, "create", "credential", cred.id, f"创建凭据 {cred.name}",
           tenant_id=cred.tenant_id)
    return cred


@router.delete("/credentials/{cred_id}", dependencies=[Depends(require_admin)])
def delete_credential(cred_id: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    cred = scoped(db.query(Credential), Credential, user).filter(
        Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="凭据不存在")
    db.delete(cred)
    db.commit()
    record(user.username, "delete", "credential", cred_id, f"删除凭据 {cred.name}",
           tenant_id=cred.tenant_id)
    return {"ok": True}


# ---- 审计日志已迁至 app/api/audit.py（支持筛选、分页、导出）----


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""
