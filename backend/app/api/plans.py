"""巡检计划、巡检报告、告警配置。"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_write
from app.api.scope import scoped, scope_tenant_id
from app.core.database import get_db, SessionLocal
from app.models import (
    InspectionPlan, InspectionTemplate, InspectionReport,
    Host, HostGroup, Task, PlanRun, User, DEFAULT_TENANT_ID,
)
from app.schemas import (
    PlanCreate, PlanOut, ReportOut, CronPreviewRequest, CronPreviewResponse,
)
from app.services import scheduler
from app.services.alert import evaluate_task
from app.services.artifact import store as artifact_store, artifact_key
from app.executor import executor

logger = logging.getLogger("autoops.plans")
router = APIRouter(prefix="/plans", tags=["plans"], dependencies=[Depends(get_current_user)])


def _tenant_of(user: User) -> str:
    return scope_tenant_id(user) or user.tenant_id or DEFAULT_TENANT_ID


# ---- 巡检计划 ----
@router.get("", response_model=List[PlanOut])
def list_plans(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl_map = {t.id: t.name for t in scoped(
        db.query(InspectionTemplate), InspectionTemplate, user).all()}
    plans = scoped(db.query(InspectionPlan), InspectionPlan, user).order_by(
        InspectionPlan.created_at.desc()).all()
    return [
        PlanOut(
            id=p.id, name=p.name, template_id=p.template_id,
            template_name=tpl_map.get(p.template_id), target_type=p.target_type,
            target_id=p.target_id, cron=p.cron, enabled=p.enabled,
            last_run_at=p.last_run_at, created_at=p.created_at,
        ) for p in plans
    ]


@router.post("", response_model=PlanOut)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), user=Depends(require_write)):
    data = payload.model_dump()
    if data.get("template_id"):
        tpl = scoped(db.query(InspectionTemplate), InspectionTemplate, user).filter(
            InspectionTemplate.id == data["template_id"]).first()
        if not tpl:
            raise HTTPException(status_code=404, detail="巡检模板不存在")
    plan = InspectionPlan(**data, tenant_id=_tenant_of(user))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    if plan.enabled and plan.cron:
        scheduler.register_plan(plan.id, plan.cron, run_plan_job)
    return _plan_out(plan, db)


@router.put("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: str, payload: PlanCreate, db: Session = Depends(get_db),
                user=Depends(require_write)):
    plan = scoped(db.query(InspectionPlan), InspectionPlan, user).filter(
        InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    for k, v in payload.model_dump().items():
        setattr(plan, k, v)
    db.commit()
    db.refresh(plan)
    if plan.enabled and plan.cron:
        scheduler.register_plan(plan.id, plan.cron, run_plan_job)
    else:
        scheduler.unregister_plan(plan.id)
    return _plan_out(plan, db)


@router.delete("/{plan_id}")
def delete_plan(plan_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    plan = scoped(db.query(InspectionPlan), InspectionPlan, user).filter(
        InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    scheduler.unregister_plan(plan_id)
    db.delete(plan)
    db.commit()
    return {"ok": True}


@router.post("/{plan_id}/run")
def run_plan_now(plan_id: str, db: Session = Depends(get_db), user=Depends(require_write)):
    """手动立即执行一次巡检计划（不参与去重，永远执行）。"""
    plan = scoped(db.query(InspectionPlan), InspectionPlan, user).filter(
        InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    report_id = run_plan_job(plan_id, trigger="manual")
    if not report_id:
        raise HTTPException(status_code=400, detail="执行失败：模板或目标主机缺失")
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
def run_plan_job(plan_id: str, run_key: Optional[str] = None, trigger: str = "manual"):
    """执行一次巡检。

    run_key：定时触发时传入「计划@时间槽」，用唯一约束保证多实例下同一时间槽只执行一次。
    返回 report_id；被去重或前置条件不满足时返回 None。
    """
    if run_key and not scheduler.claim_run_key(plan_id, run_key):
        logger.info("计划 %s 时间槽 %s 已由其他实例执行，跳过", plan_id, run_key)
        return None

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
            target_id=plan.target_id, created_by=f"scheduler:{trigger}",
            tenant_id=plan.tenant_id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

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
            tenant_id=plan.tenant_id,
        )
        db.add(report)
        db.commit()
        report_id = report.id

        # 报告归档 + 任务明细归档
        report.artifact_uri = _archive_report(report, task_id)
        task.artifact_uri = _archive_task_bundle(db, task)
        if run_key:
            run = db.query(PlanRun).filter(PlanRun.run_key == run_key).first()
            if run:
                run.report_id = report_id
        db.commit()

        # 告警：走状态机（首次异常提醒一次，恢复时补恢复通知）
        evaluate_task(db, task, resource_type="plan", resource_id=plan.id,
                      extra={"计划": plan.name, "模板": tpl.name})

        return report_id
    finally:
        db.close()


def _archive_report(report: InspectionReport, task_id: str) -> str:
    try:
        return artifact_store.put_json(
            artifact_key(f"tenants/{report.tenant_id}/reports", report.id),
            {
                "schema": "autoops.inspection_report.v1",
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "report": {
                    "id": report.id, "plan_id": report.plan_id,
                    "plan_name": report.plan_name, "template_name": report.template_name,
                    "task_id": task_id, "status": report.status,
                    "summary": report.summary, "content": report.content,
                    "created_at": report.created_at.isoformat() if report.created_at else None,
                },
            },
        )
    except Exception as e:
        logger.warning("报告 %s 归档失败: %s", report.id, e)
        return ""


def _archive_task_bundle(db: Session, task: Task) -> str:
    try:
        from app.models import TaskLog
        logs = db.query(TaskLog).filter(TaskLog.task_id == task.id).all()
        return artifact_store.put_json(
            artifact_key(f"tenants/{task.tenant_id}/tasks", task.id),
            {
                "schema": "autoops.task.v1",
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "task": {
                    "id": task.id, "name": task.name, "task_type": task.task_type,
                    "status": task.status, "summary": task.summary,
                    "target_type": task.target_type, "target_id": task.target_id,
                    "created_by": task.created_by,
                    "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                },
                "logs": [{"host": l.host, "event": l.event, "message": l.message,
                          "stdout": l.stdout} for l in logs],
            },
        )
    except Exception as e:
        logger.warning("巡检任务 %s 归档失败: %s", task.id, e)
        return ""


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
    return "\n".join([
        f"巡检模板: {tpl.name}",
        f"执行结果: ok={summary.get('ok',0)} failed={summary.get('failed',0)} "
        f"unreachable={summary.get('unreachable',0)} changed={summary.get('changed',0)}",
    ])


# ---- 巡检报告 ----
@router.get("/reports", response_model=List[ReportOut])
def list_reports(plan_id: str = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    q = scoped(db.query(InspectionReport), InspectionReport, user)
    if plan_id:
        q = q.filter(InspectionReport.plan_id == plan_id)
    return q.order_by(InspectionReport.created_at.desc()).limit(200).all()


@router.get("/reports/{report_id}/artifact")
def get_report_artifact(report_id: str, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    report = scoped(db.query(InspectionReport), InspectionReport, user).filter(
        InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not report.artifact_uri:
        raise HTTPException(status_code=404, detail="该报告尚未归档产物")
    url = artifact_store.presigned_url(report.artifact_uri)
    if url:
        return {"url": url, "backend": "s3"}
    path = artifact_store.local_file(report.artifact_uri)
    if not path:
        raise HTTPException(status_code=404, detail="产物文件已被清理")
    return FileResponse(path, media_type="application/gzip",
                        filename=f"report-{report.id}.json.gz")


# ---- cron 预览 ----
@router.post("/cron/preview", response_model=CronPreviewResponse)
def preview_cron(payload: CronPreviewRequest):
    """校验 cron 并给出接下来几次执行时间，供前端可视化编辑器即时反馈。"""
    from app.services.scheduler import _cron_to_trigger, describe_cron, resolve_cron

    try:
        trigger = _cron_to_trigger(payload.cron)
    except Exception as e:
        return CronPreviewResponse(valid=False, expression=payload.cron, error=str(e))

    expr = resolve_cron(payload.cron)
    now = datetime.now()
    runs, cursor = [], now
    for _ in range(max(1, min(payload.count, 10))):
        nxt = trigger.get_next_fire_time(None, cursor)
        if not nxt:
            break
        runs.append(nxt)
        cursor = nxt
    return CronPreviewResponse(
        valid=True, expression=expr, description=describe_cron(expr),
        next_runs=runs,
    )


# ---- 报告导出 ----
@router.get("/reports/{report_id}/export")
def export_report(report_id: str, format: str = "pdf", db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """导出巡检报告为 PDF 或 Excel（含逐主机明细）。"""
    from app.services.export import build_report_pdf, build_report_xlsx

    report = scoped(db.query(InspectionReport), InspectionReport, user).filter(
        InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    fmt = (format or "pdf").lower()
    stamp = report.created_at.strftime("%Y%m%d-%H%M") if report.created_at else "report"
    try:
        if fmt == "xlsx":
            path = build_report_xlsx(db, report)
            return FileResponse(
                path, filename=f"巡检报告-{report.plan_name}-{stamp}.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if fmt == "pdf":
            path = build_report_pdf(db, report)
            return FileResponse(path, filename=f"巡检报告-{report.plan_name}-{stamp}.pdf",
                                media_type="application/pdf")
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    raise HTTPException(status_code=400, detail="format 仅支持 pdf / xlsx")


# ---- 报告列表筛选 ----
@router.get("/reports/export-all")
def export_all_reports(format: str = "xlsx", days: int = 30,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """导出近 N 天全部巡检报告汇总表。"""
    from datetime import timedelta
    from app.services.export import build_reports_xlsx

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, days))
    rows = scoped(db.query(InspectionReport), InspectionReport, user).filter(
        InspectionReport.created_at >= since).order_by(
        InspectionReport.created_at.desc()).all()
    path = build_reports_xlsx(rows)
    return FileResponse(
        path, filename=f"巡检报告汇总-近{days}天.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

