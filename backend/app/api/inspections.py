"""巡检模板与自然语言生成。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import InspectionTemplate
from app.schemas import TemplateCreate, TemplateOut, NL2PlaybookRequest, NL2PlaybookResponse
from app.services.llm import generate_playbook

router = APIRouter(prefix="/inspections", tags=["inspections"], dependencies=[Depends(get_current_user)])


@router.get("/templates", response_model=List[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.query(InspectionTemplate).order_by(InspectionTemplate.updated_at.desc()).all()


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    tpl = InspectionTemplate(**payload.model_dump())
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.put("/templates/{tpl_id}", response_model=TemplateOut)
def update_template(tpl_id: str, payload: TemplateCreate, db: Session = Depends(get_db)):
    tpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == tpl_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    for k, v in payload.model_dump().items():
        setattr(tpl, k, v)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/templates/{tpl_id}")
def delete_template(tpl_id: str, db: Session = Depends(get_db)):
    tpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == tpl_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(tpl)
    db.commit()
    return {"ok": True}


@router.post("/generate", response_model=NL2PlaybookResponse)
def nl2playbook(payload: NL2PlaybookRequest):
    result = generate_playbook(payload.prompt, payload.category)
    return NL2PlaybookResponse(**result)
