"""调度器：基于 APScheduler 的进程内定时任务。

巡检计划用 cron 表达式注册，到点自动执行巡检并生成报告。
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger("autoops.scheduler")

scheduler = BackgroundScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone="Asia/Shanghai",
)


def _cron_to_trigger(cron: str) -> CronTrigger:
    """支持两种格式：5段 cron '分 时 日 月 周'，或预设 'daily/hours/...'。"""
    preset = {
        "daily": "0 2 * * *",
        "hourly": "0 * * * *",
        "every30min": "*/30 * * * *",
    }
    expr = preset.get(cron, cron)
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"无效 cron 表达式: {cron}")
    minute, hour, day, month, dow = parts
    return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow)


def register_plan(plan_id: str, cron: str, job_func):
    """注册/更新巡检计划的定时任务。"""
    job_id = f"inspection_plan_{plan_id}"
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        trigger = _cron_to_trigger(cron)
        scheduler.add_job(job_func, trigger, id=job_id, args=[plan_id], replace_existing=True)
        logger.info("已注册巡检计划 %s，cron=%s", plan_id, cron)
    except Exception as e:
        logger.error("注册巡检计划 %s 失败: %s", plan_id, e)


def unregister_plan(plan_id: str):
    job_id = f"inspection_plan_{plan_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def start():
    if not scheduler.running:
        scheduler.start()
        logger.info("调度器已启动")


def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
