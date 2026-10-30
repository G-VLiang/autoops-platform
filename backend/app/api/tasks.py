"""任务：批量执行（adhoc/playbook/巡检）、失败重试、超时控制、作业模板库。"""
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rbac import require_execute
from app.api.scope import scoped, scope_tenant_id
from app.core.database import get_db
from app.executor import executor
from app.models import Task, TaskLog, Host, HostGroup, InspectionTemplate, User, DEFAULT_TENANT_ID
from app.schemas import (
    TaskCreate, TaskOut, TaskLogOut, LibraryItem, TaskFromLibrary,
)
from app.services import job_library
from app.services.alert import evaluate_task
from app.services.artifact import store as artifact_store, artifact_key
from app.services.audit import record

logger = logging.getLogger("autoops.tasks")
router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)])


def _tenant_of(user: User) -> str:
    return scope_tenant_id(user) or user.tenant_id or DEFAULT_TENANT_ID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _resolve_targets(target_type: str, target_id: str, db: Session, user: User) -> List[dict]:
    if target_type == "group":
        group = scoped(db.query(HostGroup), HostGroup, user).filter(
            HostGroup.id == target_id).first()
        if not group:
            return []
        return [{"hostname": h.hostname, "ip": h.ip, "port": h.port} for h in group.hosts]
    host = scoped(db.query(Host), Host, user).filter(Host.id == target_id).first()
    if not host:
        return []
    return [{"hostname": host.hostname, "ip": host.ip, "port": host.port}]


@router.get("", response_model=List[TaskOut])
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return scoped(db.query(Task), Task, user).order_by(Task.created_at.desc()).limit(100).all()


# ---- 作业模板库（放在 /{task_id} 之前，避免被路径参数吞掉）----
@router.get("/library", response_model=List[LibraryItem])
def list_library(category: Optional[str] = None, keyword: Optional[str] = None):
    return [LibraryItem(**item) for item in job_library.list_items(category, keyword)]


@router.get("/library/categories")
def library_categories():
    cats: dict[str, int] = {}
    for item in job_library.LIBRARY:
        cats[item["category"]] = cats.get(item["category"], 0) + 1
    return [{"category": k, "count": v} for k, v in sorted(cats.items())]


@router.post("/from-library", response_model=TaskOut)
def create_from_library(payload: TaskFromLibrary, db: Session = Depends(get_db),
                        user=Depends(require_execute)):
    item = job_library.get_item(payload.library_key)
    if not item:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not payload.target_id:
        raise HTTPException(status_code=400, detail="请选择执行目标")

    task = Task(
        name=payload.name or item["name"], task_type="playbook", content=item["content"],
        target_type=payload.target_type, target_id=payload.target_id,
        created_by=user.username, tenant_id=_tenant_of(user),
        max_retries=max(0, payload.max_retries),
        timeout_seconds=max(0, payload.timeout_seconds),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    _run_and_record(task, db, user)
    db.refresh(task)
    record(user.username, "execute", "task", task.id,
           f"执行模板任务 {task.name}（{payload.library_key}）结果 {task.status}",
           tenant_id=task.tenant_id)
    return task


@router.post("", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db),
                user=Depends(require_execute)):
    content = payload.content
    if payload.task_type == "inspection":
        tpl = scoped(db.query(InspectionTemplate), InspectionTemplate, user).filter(
            InspectionTemplate.id == payload.content).first()
        if not tpl:
            raise HTTPException(status_code=404, detail="巡检模板不存在")
        content = tpl.playbook

    task = Task(
        name=payload.name, task_type=payload.task_type, content=content,
        target_type=payload.target_type, target_id=payload.target_id,
        created_by=user.username, tenant_id=_tenant_of(user),
        max_retries=max(0, payload.max_retries),
        timeout_seconds=max(0, payload.timeout_seconds),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    _run_and_record(task, db, user)
    db.refresh(task)
    record(user.username, "execute", "task", task.id,
           f"执行任务 {task.name} 结果 {task.status}", tenant_id=task.tenant_id)
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = scoped(db.query(Task), Task, user).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/logs", response_model=List[TaskLogOut])
def get_task_logs(task_id: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    task = scoped(db.query(Task), Task, user).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return db.query(TaskLog).filter(TaskLog.task_id == task_id).order_by(
        TaskLog.created_at.asc()).all()


@router.get("/{task_id}/artifact")
def get_task_artifact(task_id: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """下载归档的执行明细。S3 后端返回预签名链接，本地后端直接流式返回文件。"""
    task = scoped(db.query(Task), Task, user).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.artifact_uri:
        raise HTTPException(status_code=404, detail="该任务尚未归档产物")
    url = artifact_store.presigned_url(task.artifact_uri)
    if url:
        return {"url": url, "backend": "s3"}
    path = artifact_store.local_file(task.artifact_uri)
    if not path:
        raise HTTPException(status_code=404, detail="产物文件已被清理")
    return FileResponse(path, media_type="application/gzip",
                        filename=f"task-{task.id}.json.gz")


# ---------------------------------------------------------------- 执行核心
def _execute_once(task: Task, db: Session, targets: List[dict],
                  deadline: Optional[float]) -> tuple[dict, bool]:
    """执行一轮，返回 (summary, timed_out)。deadline 为 time.monotonic() 绝对时间。"""
    summary = {"ok": 0, "changed": 0, "failed": 0, "unreachable": 0}
    timed_out = False
    for event in executor.run(task.task_type, task.content, targets):
        if deadline and time.monotonic() > deadline:
            timed_out = True
            db.add(TaskLog(task_id=task.id, host="all", event="info",
                           message=f"整体执行超时（{task.timeout_seconds}s），已中止后续主机的执行"))
            db.flush()
            break
        if event["event"] == "summary":
            summary = event.get("summary", summary)
            continue
        db.add(TaskLog(
            task_id=task.id, host=event.get("host", ""), event=event["event"],
            message=event.get("message", ""), stdout=event.get("stdout", ""),
        ))
    db.flush()
    return summary, timed_out


def _run_and_record(task: Task, db: Session, user: User):
    targets = _resolve_targets(task.target_type, task.target_id, db, user)
    task.status = "running"
    task.started_at = _utcnow()
    db.commit()

    summary = {"ok": 0, "changed": 0, "failed": 0, "unreachable": 0}
    total_attempts = max(1, (task.max_retries or 0) + 1)

    for attempt in range(1, total_attempts + 1):
        task.attempts = attempt
        deadline = (time.monotonic() + task.timeout_seconds) if task.timeout_seconds else None
        summary, timed_out = _execute_once(task, db, targets, deadline)

        if timed_out:
            status = "failed" if summary["ok"] == 0 else "partial"
        elif summary["unreachable"] > 0 or summary["failed"] > 0:
            status = "failed" if summary["ok"] == 0 else "partial"
        else:
            status = "success"

        if status == "success" or attempt >= total_attempts:
            task.status = status
            break

        # 还有重试机会：记一条分隔日志后重来
        db.add(TaskLog(
            task_id=task.id, host="all", event="info",
            message=f"第 {attempt} 次执行结果 {status}，准备第 {attempt + 1} 次重试",
        ))
        db.flush()
        time.sleep(min(2 ** (attempt - 1), 5))

    task.summary = summary
    task.finished_at = _utcnow()
    db.commit()

    # 告警：首次失败提醒，恢复时补恢复通知（按 fingerprint 去重）
    try:
        evaluate_task(db, task, resource_type="task", resource_id=task.id)
    except Exception as e:
        logger.warning("任务 %s 告警处理失败: %s", task.id, e)
        db.rollback()

    task.artifact_uri = _archive_task(db, task, user)
    db.commit()


def _archive_task(db: Session, task: Task, user: User) -> str:
    """归档明细到产物存储。失败只记日志，不影响任务结果。"""
    try:
        logs = db.query(TaskLog).filter(TaskLog.task_id == task.id).order_by(
            TaskLog.created_at.asc()).all()
        bundle = {
            "schema": "autoops.task.v1",
            "archived_at": _utcnow().isoformat(),
            "tenant_id": task.tenant_id,
            "task": {
                "id": task.id, "name": task.name, "task_type": task.task_type,
                "content": task.content, "target_type": task.target_type,
                "target_id": task.target_id, "status": task.status,
                "summary": task.summary, "created_by": task.created_by,
                "attempts": task.attempts, "max_retries": task.max_retries,
                "timeout_seconds": task.timeout_seconds,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            },
            "logs": [
                {"host": l.host, "event": l.event, "message": l.message,
                 "stdout": l.stdout,
                 "created_at": l.created_at.isoformat() if l.created_at else None}
                for l in logs
            ],
        }
        return artifact_store.put_json(artifact_key(f"tenants/{task.tenant_id}/tasks", task.id), bundle)
    except Exception as e:
        logger.warning("任务 %s 产物归档失败（不影响执行结果）: %s", task.id, e)
        return ""
