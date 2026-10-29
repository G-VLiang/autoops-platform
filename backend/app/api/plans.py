"""巡检计划、巡检报告、告警配置。"""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db, SessionLocal
from app.models import (
    InspectionPlan, InspectionTemplate, InspectionReport,
    AlertConfig, Host, HostGroup, Task,
)
from app.schemas import (
    PlanCreate, PlanOut, ReportOut, AlertConfigCreate, AlertConfigOut,
)
from app.services import scheduler
from app.services.alert import send_alert
from app.executor import executor

router = APIRouter(prefix="/plans", tags=["plans"], dependencies=[Depends(get_current_user)])


# ---- 巡检计划 ----
@router.get("", response_model=List[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    tpl_map = {t.id: t.name for t in db.query(InspectionTemplate).all()}
    plans = db.query(InspectionPlan).order_by(InspectionPlan.created_at.desc()).all()
    result = []
    for p in plans:
        result.append(PlanOut(
            id=p.id, name=p.name, template_id=p.template_id,
            template_name=tpl_map.get(p.template_id), target_type=p.target_type,
            target_id=p.target_id, cron=p.cron, enabled=p.enabled,
            last_run_at=p.last_run_at, created_at=p.created_at,
        ))
    return result


@router.post("", response_model=PlanOut)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    plan = InspectionPlan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    if plan.enabled and plan.cron:
        scheduler.register_plan(plan.id, plan.cron, run_plan_job)
    return _plan_out(plan, db)


@router.put("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: str, payload: PlanCreate, db: Session = Depends(get_db)):
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    for k, v in payload.model_dump().items():
        setattr(plan, k, v)
    db.commit()
    db.refresh(plan)
    # 重新注册调度
    if plan.enabled and plan.cron:
        scheduler.register_plan(plan.id, plan.cron, run_plan_job)
    else:
        scheduler.unregister_plan(plan.id)
    return _plan_out(plan, db)


@router.delete("/{plan_id}")
def delete_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    scheduler.unregister_plan(plan_id)
    db.delete(plan)
    db.commit()
    return {"ok": True}


@router.post("/{plan_id}/run")
def run_plan_now(plan_id: str, db: Session = Depends(get_db)):
    """手动立即执行一次巡检计划。"""
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    report_id = run_plan_job(plan_id)
    return {"ok": True, "report_id": report_id}


def _plan_out(plan: InspectionPlan, db: Session) -> PlanOut:
    tpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == plan.template_id).first()
    return PlanOut(
        id=plan.id, name=plan.name, template_id=plan.template_id,
        template_name=tpl.name if tpl else None, target_type=plan.target_type,
        target_id=plan.target_id, cron=plan.cron, enabled=plan.enabled,
        last_run_at=plan.last_run_at, created_at=plan.created_at,
    )


# ---- 巡检执行核心（供调度器调用）----
def run_plan_job(plan_id: str):
    db = SessionLocal()
    try:
        plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
        if not plan:
            return None
        tpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == plan.template_id).first()
        if not tpl:
            return None

        targets = _resolve_targets(plan.target_type, plan.target_id, db)
        task = Task(
            name=f"[巡检] {plan.name}", task_type="inspection",
            content=tpl.playbook, target_type=plan.target_type,
            target_id=plan.target_id, created_by="scheduler",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # 执行
        summary = {"ok": 0, "changed": 0, "failed": 0, "unreachable": 0}
        for event in executor.run("inspection", tpl.playbook, targets):
            if event["event"] == "summary":
                summary = event.get("summary", summary)

        if summary["unreachable"] > 0 or summary["failed"] > 0:
            status = "failed" if summary["ok"] == 0 else "partial"
        else:
            status = "success"
        task.status = status
        task.summary = summary
        task.finished_at = datetime.now(timezone.utc)
        plan.last_run_at = datetime.now(timezone.utc)

        report = InspectionReport(
            plan_id=plan.id, plan_name=plan.name, template_name=tpl.name,
            task_id=task.id, status=status, summary=summary,
            content=_build_report_content(tpl, summary),
        )
        db.add(report)
        db.commit()
        report_id = report.id

        # 异常告警
        if status != "success":
            configs = db.query(AlertConfig).filter(AlertConfig.enabled == True).all()
            from app.services.alert import notify_task_result
            notify_task_result(task, configs)

        return report_id
    finally:
        db.close()


def _resolve_targets(target_type: str, target_id: str, db: Session) -> List[dict]:
    if target_type == "group":
        group = db.query(HostGroup).filter(HostGroup.id == target_id).first()
        if not group:
            return []
        return [{"hostname": h.hostname, "ip": h.ip, "port": h.port} for h in group.hosts]
    host = db.query(Host).filter(Host.id == target_id).first()
    if not host:
        return []
    return [{"hostname": host.hostname, "ip": host.ip, "port": host.port}]


def _build_report_content(tpl: InspectionTemplate, summary: dict) -> str:
    lines = [
        f"巡检模板: {tpl.name}",
        f"执行结果: ok={summary.get('ok',0)} failed={summary.get('failed',0)} "
        f"unreachable={summary.get('unreachable',0)} changed={summary.get('changed',0)}",
    ]
    return "\n".join(lines)


# ---- 巡检报告 ----
@router.get("/reports", response_model=List[ReportOut])
def list_reports(plan_id: str = None, db: Session = Depends(get_db)):
    q = db.query(InspectionReport)
    if plan_id:
        q = q.filter(InspectionReport.plan_id == plan_id)
    return q.order_by(InspectionReport.created_at.desc()).limit(100).all()


# ---- 告警配置 ----
@router.get("/alerts", response_model=List[AlertConfigOut])
def list_alerts(db: Session = Depends(get_db)):
    return db.query(AlertConfig).all()


@router.post("/alerts", response_model=AlertConfigOut)
def create_alert(payload: AlertConfigCreate, db: Session = Depends(get_db)):
    cfg = AlertConfig(**payload.model_dump())
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str, db: Session = Depends(get_db)):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == alert_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    db.delete(cfg)
    db.commit()
    return {"ok": True}


@router.post("/alerts/{alert_id}/test")
def test_alert(alert_id: str, db: Session = Depends(get_db)):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == alert_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    ok = send_alert(cfg.webhook_url, cfg.channel, "告警测试", {"来源": "手动测试"})
    return {"ok": ok, "sent": bool(cfg.webhook_url)}
