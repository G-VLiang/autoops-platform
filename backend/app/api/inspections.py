"""巡检模板与自然语言生成。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_write
from app.api.scope import scoped, scope_tenant_id
from app.core.database import get_db
from app.models import InspectionTemplate, User, DEFAULT_TENANT_ID
from app.schemas import TemplateCreate, TemplateOut, NL2PlaybookRequest, NL2PlaybookResponse
from app.services.llm import generate_playbook

router = APIRouter(prefix="/inspections", tags=["inspections"], dependencies=[Depends(get_current_user)])


@router.get("/templates", response_model=List[TemplateOut])
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return scoped(db.query(InspectionTemplate), InspectionTemplate, user).order_by(
        InspectionTemplate.updated_at.desc()).all()


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db),
                    user=Depends(require_write)):
    tpl = InspectionTemplate(
        **payload.model_dump(),
        tenant_id=scope_tenant_id(user) or user.tenant_id or DEFAULT_TENANT_ID,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.put("/templates/{tpl_id}", response_model=TemplateOut)
def update_template(tpl_id: str, payload: TemplateCreate, db: Session = Depends(get_db),
                    user=Depends(require_write)):
    tpl = scoped(db.query(InspectionTemplate), InspectionTemplate, user).filter(
        InspectionTemplate.id == tpl_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    for k, v in payload.model_dump().items():
        setattr(tpl, k, v)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/templates/{tpl_id}")
def delete_template(tpl_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    tpl = scoped(db.query(InspectionTemplate), InspectionTemplate, user).filter(
        InspectionTemplate.id == tpl_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(tpl)
    db.commit()
    return {"ok": True}


@router.post("/generate", response_model=NL2PlaybookResponse)
def nl2playbook(payload: NL2PlaybookRequest):
    result = generate_playbook(payload.prompt, payload.category)
    return NL2PlaybookResponse(**result)
