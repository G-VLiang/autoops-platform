"""调度器：APScheduler + 数据库租约选主，支持多实例部署。

单机时行为与原来一致（本机即 leader）。多副本部署时：
- 各实例启动后竞争 `scheduler_locks` 中名为 scheduler 的租约，只有一个成为 leader；
- leader 每 SCHEDULER_HEARTBEAT 秒续约（expires_at 往后推），其余实例 standby；
- leader 挂掉后租约过期，standby 在下一轮心跳中抢占并接管任务；
- 即使出现瞬时双 leader，计划级 `plan_runs` 唯一约束也会把同一时间槽的重复执行挡掉。
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import SchedulerLock, InspectionPlan, PlanRun

logger = logging.getLogger("autoops.scheduler")

LOCK_NAME = "scheduler"

# 角色常量
ROLE_LEADER = "leader"
ROLE_STANDBY = "standby"
ROLE_DISABLED = "disabled"

scheduler = BackgroundScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone="Asia/Shanghai",
)


def instance_id() -> str:
    return settings.INSTANCE_ID or f"{socket.gethostname()}-{os.getpid()}"


class LeaderElection:
    """基于数据库行锁语义的租约选主（SQLite / PostgreSQL 通用）。"""

    def __init__(self):
        self.id = instance_id()
        self.role = ROLE_DISABLED if not settings.SCHEDULER_ENABLED else ROLE_STANDBY
        self.lease_until: datetime | None = None
        self.last_error: str = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._job_loader = None    # 成为 leader 时调用：注册所有启用的计划
        self._job_clearer = None   # 失去 leader 时调用：清空本地作业

    # ---- 租约 ----
    def _ensure_row(self) -> None:
        db = SessionLocal()
        try:
            row = db.query(SchedulerLock).filter(SchedulerLock.name == LOCK_NAME).first()
            if not row:
                db.add(SchedulerLock(name=LOCK_NAME, holder="", expires_at=None))
                try:
                    db.commit()
                except Exception:
                    db.rollback()   # 并发插入冲突，说明别的实例已建好
        finally:
            db.close()

    def try_acquire(self) -> bool:
        """抢占或续约。返回 True 表示当前持有租约。"""
        now = datetime.utcnow()
        expires = now + timedelta(seconds=settings.SCHEDULER_LEASE_TTL)
        db = SessionLocal()
        try:
            # 单条 UPDATE 完成「判断 + 占用」，避免两次查询之间的竞态
            updated = db.query(SchedulerLock).filter(
                SchedulerLock.name == LOCK_NAME,
                (SchedulerLock.holder == self.id)
                | (SchedulerLock.holder == "")
                | (SchedulerLock.expires_at.is_(None))
                | (SchedulerLock.expires_at < now),
            ).update(
                {"holder": self.id, "acquired_at": now, "expires_at": expires},
                synchronize_session=False,
            )
            db.commit()
            if updated:
                self.lease_until = expires
                return True
            return False
        except Exception as e:
            db.rollback()
            self.last_error = str(e)
            logger.warning("租约更新失败: %s", e)
            return False
        finally:
            db.close()

    def release(self) -> None:
        db = SessionLocal()
        try:
            db.query(SchedulerLock).filter(
                SchedulerLock.name == LOCK_NAME, SchedulerLock.holder == self.id
            ).update({"holder": "", "expires_at": None}, synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    # ---- 角色切换 ----
    def _become_leader(self) -> None:
        if self.role == ROLE_LEADER:
            return
        self.role = ROLE_LEADER
        logger.info("[调度] 本实例晋升为 leader: %s", self.id)
        if not scheduler.running:
            scheduler.start()
        if self._job_loader:
            self._job_loader()

    def _step_down(self) -> None:
        if self.role != ROLE_LEADER:
            return
        self.role = ROLE_STANDBY
        logger.warning("[调度] 租约丢失，降级为 standby: %s", self.id)
        if self._job_clearer:
            self._job_clearer()

    # ---- 心跳循环 ----
    def _loop(self) -> None:
        while not self._stop.wait(settings.SCHEDULER_HEARTBEAT):
            if self._stop.is_set():
                break
            acquired = self.try_acquire()
            if acquired:
                self._become_leader()
            else:
                self._step_down()

    def start(self, job_loader, job_clearer) -> None:
        self._job_loader = job_loader
        self._job_clearer = job_clearer
        if not settings.SCHEDULER_ENABLED:
            logger.info("[调度] SCHEDULER_ENABLED=false，本实例不参与选主")
            return
        # 启动时同步抢一次租约：单机场景服务就绪即为 leader，不必等第一轮心跳
        self._ensure_row()
        if self.try_acquire():
            self._become_leader()
        self._thread = threading.Thread(target=self._loop, name="scheduler-election", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self.role == ROLE_LEADER:
            self.release()
        self.role = ROLE_DISABLED

    def status(self) -> dict:
        return {
            "instance_id": self.id,
            "role": self.role,
            "lease_until": self.lease_until.isoformat() + "Z" if self.lease_until else None,
            "lease_ttl_seconds": settings.SCHEDULER_LEASE_TTL,
            "heartbeat_seconds": settings.SCHEDULER_HEARTBEAT,
            "scheduler_running": scheduler.running,
            "jobs": len(scheduler.get_jobs()) if scheduler.running else 0,
            "last_error": self.last_error,
        }


election = LeaderElection()


# ---------------------------------------------------------------- 计划作业
_PRESET_CRON = {
    "daily": "0 2 * * *",
    "hourly": "0 * * * *",
    "every30min": "*/30 * * * *",
    "weekly": "0 3 * * 1",
    "monthly": "0 4 1 * *",
}


def resolve_cron(cron: str) -> str:
    """预设别名展开为标准 5 段 cron。"""
    return _PRESET_CRON.get((cron or "").strip(), (cron or "").strip())


def describe_cron(expr: str) -> str:
    """把 cron 表达式翻译成人话（覆盖常见形态，异常时原样返回）。"""
    parts = (expr or "").split()
    if len(parts) != 5:
        return expr or "-"
    mi, ho, dom, mon, dow = parts
    weekday = {"0": "周日", "1": "周一", "2": "周二", "3": "周三", "4": "周四",
               "5": "周五", "6": "周六", "7": "周日"}

    def _time():
        if mi.isdigit() and ho.isdigit():
            return f"{int(ho):02d}:{int(mi):02d}"
        if mi.startswith("*/") and ho == "*":
            return f"每 {mi[2:]} 分钟"
        if mi.isdigit() and ho == "*":
            return f"每小时第 {int(mi)} 分"
        return f"分={mi} 时={ho}"

    t = _time()
    if dow != "*" and dom == "*":
        names = [weekday.get(d, d) for d in dow.split(",")]
        return f"{'、'.join(names)} {t}"
    if dom != "*" and dow == "*":
        return f"每月 {dom} 日 {t}"
    if dom == "*" and dow == "*":
        return f"每天 {t}"
    if mon != "*":
        return f"{mon} 月 {dom} 日 {dow} 周 {t}"
    return f"{expr}（{t}）"


def _cron_to_trigger(cron: str) -> CronTrigger:
    """支持 5 段 cron '分 时 日 月 周' 或预设别名。"""
    expr = resolve_cron(cron)
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"无效 cron 表达式: {cron}（需 5 段：分 时 日 月 周）")
    minute, hour, day, month, dow = parts
    return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow)


def _job_wrapper(plan_id: str, job_func):
    """给计划作业套一层：仅 leader 执行 + 时间槽去重。"""
    def _run():
        if election.role != ROLE_LEADER:
            return
        slot = datetime.utcnow().strftime("%Y%m%d%H%M")
        job_func(plan_id, run_key=f"{plan_id}@{slot}", trigger="schedule")
    return _run


def register_plan(plan_id: str, cron: str, job_func) -> bool:
    job_id = f"inspection_plan_{plan_id}"
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        if election.role != ROLE_LEADER:
            return False
        scheduler.add_job(_job_wrapper(plan_id, job_func), _cron_to_trigger(cron),
                          id=job_id, replace_existing=True, max_instances=1,
                          coalesce=True, misfire_grace_time=300)
        logger.info("已注册巡检计划 %s，cron=%s", plan_id, cron)
        return True
    except Exception as e:
        logger.error("注册巡检计划 %s 失败: %s", plan_id, e)
        return False


def unregister_plan(plan_id: str) -> None:
    job_id = f"inspection_plan_{plan_id}"
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except Exception as e:
        logger.warning("移除计划 %s 失败: %s", plan_id, e)


def reload_all(plan_job_func) -> None:
    """leader 上任后重建全部作业（从数据库读，保证与最新配置一致）。"""
    db = SessionLocal()
    try:
        plans = db.query(InspectionPlan).filter(InspectionPlan.enabled == True).all()  # noqa: E712
        for p in plans:
            if p.cron:
                register_plan(p.id, p.cron, plan_job_func)
        logger.info("[调度] 已加载 %s 个巡检计划", len(plans))
    finally:
        db.close()

    # 产物清理：只在 leader 上跑，避免多实例重复删除
    try:
        from app.services.artifact import store as artifact_store
        scheduler.add_job(artifact_store.cleanup, CronTrigger(hour=3, minute=30),
                          id="artifact_cleanup", replace_existing=True,
                          misfire_grace_time=3600)
    except Exception as e:
        logger.warning("注册产物清理作业失败: %s", e)

    # 主机探活：按配置间隔刷新在线状态
    if settings.HOST_PROBE_INTERVAL_MINUTES > 0:
        try:
            from app.api.hosts import probe_all_job
            scheduler.add_job(probe_all_job, "interval",
                              minutes=settings.HOST_PROBE_INTERVAL_MINUTES,
                              id="host_probe", replace_existing=True,
                              misfire_grace_time=120, max_instances=1)
            logger.info("[调度] 主机探活间隔 %s 分钟", settings.HOST_PROBE_INTERVAL_MINUTES)
        except Exception as e:
            logger.warning("注册主机探活作业失败: %s", e)

    # 告警失效清理：长时间未再上报的 firing 事件自动关闭
    if settings.ALERT_AUTO_RESOLVE_MINUTES > 0:
        try:
            from app.services.alert import resolve_stale
            from app.core.database import SessionLocal as _SL

            def _sweep():
                db = _SL()
                try:
                    n = resolve_stale(db, older_than_minutes=settings.ALERT_AUTO_RESOLVE_MINUTES)
                    if n:
                        logger.info("[告警] 自动关闭 %s 条长期未复现的告警", n)
                finally:
                    db.close()

            scheduler.add_job(_sweep, CronTrigger(minute="*/30"),
                              id="alert_sweep", replace_existing=True,
                              misfire_grace_time=600)
        except Exception as e:
            logger.warning("注册告警清理作业失败: %s", e)


def clear_jobs() -> None:
    if not scheduler.running:
        return
    for job in scheduler.get_jobs():
        try:
            scheduler.remove_job(job.id)
        except Exception:
            pass


def start(plan_job_func) -> None:
    election.start(job_loader=lambda: reload_all(plan_job_func), job_clearer=clear_jobs)


def shutdown() -> None:
    election.stop()
    if scheduler.running:
        scheduler.shutdown(wait=False)


def claim_run_key(plan_id: str, run_key: str) -> bool:
    """抢占某个执行时间槽。已存在则返回 False（跨实例幂等）。"""
    db = SessionLocal()
    try:
        db.add(PlanRun(plan_id=plan_id, run_key=run_key, instance_id=election.id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()
