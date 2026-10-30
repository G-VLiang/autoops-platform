"""系统状态：调度角色、产物存储、认证源、运行实例信息。"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.models import User
from app.services import scheduler, identity
from app.services.artifact import store as artifact_store

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(get_current_user)])


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return {
        "instance_id": scheduler.election.id,
        "api_prefix": settings.API_PREFIX,
        "database": settings.DATABASE_URL.split("://")[0],
        "executor": settings.EXECUTOR_BACKEND,
        "scheduler": scheduler.election.status(),
        "artifact": {
            "backend": artifact_store.backend,
            "dir": settings.ARTIFACT_DIR if artifact_store.backend == "local" else "",
            "bucket": settings.ARTIFACT_S3_BUCKET if artifact_store.backend == "s3" else "",
            "retention_days": settings.ARTIFACT_RETENTION_DAYS,
        },
        "auth_providers": identity.providers(),
    }


@router.post("/scheduler/reload")
def reload_scheduler(user: User = Depends(get_current_user)):
    """手动重建本实例的调度作业（改过 cron 但担心未生效时用）。"""
    from app.api.plans import run_plan_job
    scheduler.reload_all(run_plan_job)
    return {"ok": True, **scheduler.election.status()}
