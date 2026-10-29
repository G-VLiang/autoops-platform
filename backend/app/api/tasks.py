"""任务：批量执行（adhoc/playbook/巡检）与日志。"""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_execute
from app.core.database import get_db
from app.executor import executor
from app.models import Task, TaskLog, Host, HostGroup, InspectionTemplate
from app.schemas import TaskCreate, TaskOut, TaskLogOut
from app.services.audit import record

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)])


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


@router.get("", response_model=List[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.created_at.desc()).limit(100).all()


@router.post("", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), user=Depends(require_execute)):
    # 巡检类任务：content 是模板 id，需解析出 playbook
    content = payload.content
    if payload.task_type == "inspection":
        tpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == payload.content).first()
        if not tpl:
            raise HTTPException(status_code=404, detail="巡检模板不存在")
        content = tpl.playbook

    task = Task(
        name=payload.name, task_type=payload.task_type, content=content,
        target_type=payload.target_type, target_id=payload.target_id,
        created_by=user.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 同步执行（mock 快速返回；真实 ansible 可改为后台任务 + 轮询）
    _run_and_record(task, db)
    db.refresh(task)
    record(user.username, "execute", "task", task.id, f"执行任务 {task.name} 结果 {task.status}")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/logs", response_model=List[TaskLogOut])
def get_task_logs(task_id: str, db: Session = Depends(get_db)):
    return db.query(TaskLog).filter(TaskLog.task_id == task_id).order_by(TaskLog.created_at.asc()).all()


def _run_and_record(task: Task, db: Session):
    targets = _resolve_targets(task.target_type, task.target_id, db)
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.commit()

    summary = {"ok": 0, "changed": 0, "failed": 0, "unreachable": 0}
    for event in executor.run(task.task_type, task.content, targets):
        if event["event"] == "summary":
            summary = event.get("summary", summary)
            continue
        log = TaskLog(
            task_id=task.id, host=event.get("host", ""), event=event["event"],
            message=event.get("message", ""), stdout=event.get("stdout", ""),
        )
        db.add(log)
    db.flush()

    if summary["unreachable"] > 0 or summary["failed"] > 0:
        task.status = "failed" if summary["ok"] == 0 else "partial"
    else:
        task.status = "success"
    task.summary = summary
    task.finished_at = datetime.now(timezone.utc)
    db.commit()
