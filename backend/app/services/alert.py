"""告警服务：分级 + 状态机（firing/resolved）+ 静默窗口 + 去重提醒。

设计要点
--------
1. 每条告警按 fingerprint 聚合（plan:<id> / task:<id> / host:<id>）。
   同一资源连续异常只推一次，恢复时补一条「已恢复」通知，避免值班被同一问题刷屏。
2. 级别 info < warning < critical；每个通知渠道可设 min_severity 做分级路由
   （严重告警走电话群，提示类走普通群）。
3. 静默窗口内只落库不推送，用于计划内变更/维护期。
4. 未恢复的告警可按 repeat_interval_minutes 定期再提醒一次。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import AlertConfig, AlertEvent, AlertSilence

logger = logging.getLogger("autoops.alert")

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
SEVERITY_LABEL = {"info": "提示", "warning": "警告", "critical": "严重"}

_CHANNEL_PAYLOAD = {
    "dingtalk": lambda text: {"msgtype": "text", "text": {"content": text}},
    "wecom": lambda text: {"msgtype": "text", "text": {"content": text}},
    "webhook": lambda text: {"text": text},
}

# 任务/巡检状态 -> 告警级别
_STATUS_SEVERITY = {
    "failed": "critical",
    "partial": "warning",
    "unreachable": "critical",
}


def utcnow() -> datetime:
    """与数据库存储一致的 naive UTC。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def severity_of(status: str) -> str:
    return _STATUS_SEVERITY.get(status, "warning")


def _build_text(title: str, detail: dict, severity: str, resolved: bool = False) -> str:
    head = "恢复" if resolved else "告警"
    lines = [f"【AutoOps {head}】[{SEVERITY_LABEL.get(severity, severity)}] {title}"]
    for k, v in detail.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def send_alert(webhook_url: str, channel: str, title: str, detail: dict,
               severity: str = "warning", resolved: bool = False) -> bool:
    """发送单条告警，返回是否成功。未配置 url 时只记日志。"""
    if not webhook_url:
        logger.info("[告警跳过] 未配置 webhook: %s %s", title, detail)
        return False

    text = _build_text(title, detail, severity, resolved)
    payload = _CHANNEL_PAYLOAD.get(channel, _CHANNEL_PAYLOAD["webhook"])(text)
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("[告警送达] %s -> %s", title, channel)
        return True
    except Exception as e:
        logger.error("[告警失败] %s: %s", title, e)
        return False


def is_silenced(db: Session, resource_id: str, now: Optional[datetime] = None) -> bool:
    """当前时刻是否存在覆盖该资源的静默窗口。"""
    now = now or utcnow()
    row = db.query(AlertSilence).filter(
        AlertSilence.starts_at <= now,
        AlertSilence.ends_at >= now,
        or_(AlertSilence.scope == "", AlertSilence.scope == resource_id),
    ).first()
    return row is not None


def _configs(db: Session, tenant_id: str) -> Sequence[AlertConfig]:
    return db.query(AlertConfig).filter(
        AlertConfig.enabled == True,  # noqa: E712
        AlertConfig.tenant_id == tenant_id,
    ).all()


def _dispatch(configs: Sequence[AlertConfig], severity: str, title: str,
              detail: dict, resolved: bool) -> int:
    """按级别过滤后投递，返回成功渠道数。"""
    if not configs:
        logger.info("[告警无渠道] %s", title)
        return 0
    level = SEVERITY_ORDER.get(severity, 1)
    sent = 0
    for cfg in configs:
        if SEVERITY_ORDER.get(cfg.min_severity or "info", 0) > level:
            continue    # 该渠道只关心更高级别的告警
        if send_alert(cfg.webhook_url, cfg.channel, title, detail, severity, resolved):
            sent += 1
    return sent


def evaluate(db: Session, *, fingerprint: str, title: str, severity: str,
             resource_type: str, resource_id: str, detail: dict,
             tenant_id: str, healthy: bool) -> dict:
    """上报一次观测结果，驱动告警状态机。

    healthy=True 表示本次观测正常（用于判定恢复）；否则按 severity 告警。
    返回 {"action": created|repeated|resolved|silenced|skipped, "notified": n}
    """
    now = utcnow()
    ev = db.query(AlertEvent).filter(AlertEvent.fingerprint == fingerprint).first()
    configs = _configs(db, tenant_id)

    # ---- 健康：有未恢复事件则关闭并发恢复通知 ----
    if healthy:
        if not ev or ev.status != "firing":
            return {"action": "skipped", "notified": 0}
        duration_min = int((now - (ev.first_seen_at or now)).total_seconds() // 60)
        ev.status = "resolved"
        ev.resolved_at = now
        ev.last_seen_at = now
        notified = 0
        if not is_silenced(db, resource_id, now):
            notified = _dispatch(
                configs, ev.severity, f"已恢复: {ev.title}",
                {
                    "资源": f"{ev.resource_type}#{ev.resource_id}",
                    "持续时长": f"{duration_min} 分钟",
                    "异常次数": ev.occurrences,
                    "恢复时间": now.strftime("%Y-%m-%d %H:%M:%S"),
                },
                resolved=True,
            )
            if notified:
                ev.last_notified_at = now
        db.commit()
        logger.info("[告警恢复] %s 持续 %s 分钟", ev.title, duration_min)
        return {"action": "resolved", "notified": notified}

    # ---- 异常 ----
    if ev is None:
        ev = AlertEvent(
            fingerprint=fingerprint, title=title, severity=severity, status="firing",
            resource_type=resource_type, resource_id=resource_id, detail=detail,
            occurrences=1, first_seen_at=now, last_seen_at=now, tenant_id=tenant_id,
        )
        db.add(ev)
        need_notify = True
    else:
        # 已恢复的告警再次触发：视为新一轮，重置首见时间
        reopened = ev.status == "resolved"
        if reopened:
            ev.status = "firing"
            ev.resolved_at = None
            ev.first_seen_at = now
            ev.occurrences = 1
        else:
            ev.occurrences += 1
        ev.title = title
        ev.severity = severity
        ev.detail = detail
        ev.last_seen_at = now
        need_notify = reopened
        if not need_notify:
            # 未恢复的重复异常：仅在配置了重复提醒间隔且到期时再推一次
            interval = max([c.repeat_interval_minutes or 0 for c in configs] or [0])
            if interval > 0:
                last = ev.last_notified_at or ev.first_seen_at or now
                need_notify = (now - last) >= timedelta(minutes=interval)

    if is_silenced(db, resource_id, now):
        db.commit()
        logger.info("[告警静默] %s（静默窗口内，仅记录）", title)
        return {"action": "silenced", "notified": 0}

    if not need_notify:
        db.commit()
        return {"action": "skipped", "notified": 0}

    notified = _dispatch(configs, severity, title, detail, resolved=False)
    if notified:
        ev.last_notified_at = now
    db.commit()
    logger.info("[告警触发] %s 级别=%s 渠道=%s 次数=%s", title, severity, notified, ev.occurrences)
    return {"action": "created" if ev.occurrences == 1 else "repeated", "notified": notified}


def evaluate_task(db: Session, task, resource_type: str = "task",
                  resource_id: Optional[str] = None, extra: Optional[dict] = None) -> dict:
    """任务执行结果上报：成功即恢复，失败按状态分级。"""
    healthy = task.status in ("success", "pending", "running")
    severity = severity_of(task.status)
    detail = {
        "任务": task.name,
        "类型": task.task_type,
        "状态": task.status,
        "结果": str(task.summary or {}),
        "执行次数": getattr(task, "attempts", 1),
        "时间": task.finished_at.strftime("%Y-%m-%d %H:%M:%S") if task.finished_at else "-",
    }
    if extra:
        detail.update(extra)
    rid = resource_id or task.id
    prefix = "plan" if resource_type == "plan" else "task"
    return evaluate(
        db,
        fingerprint=f"{prefix}:{rid}",
        title=("巡检计划异常" if resource_type == "plan" else "任务异常") + f": {task.name}",
        severity=severity,
        resource_type=resource_type,
        resource_id=rid,
        detail=detail,
        tenant_id=task.tenant_id,
        healthy=healthy,
    )


def notify_task_result(task, enabled_configs) -> None:
    """兼容旧调用：直接把任务结果推到给定渠道（不做状态机）。"""
    if task.status not in ("failed", "partial"):
        return
    detail = {
        "任务": task.name,
        "类型": task.task_type,
        "状态": task.status,
        "结果": str(task.summary),
        "时间": str(task.finished_at),
    }
    for cfg in enabled_configs:
        send_alert(cfg.webhook_url, cfg.channel, f"任务异常: {task.name}", detail,
                   severity_of(task.status))


def resolve_stale(db: Session, tenant_id: Optional[str] = None,
                  older_than_minutes: int = 0) -> int:
    """把长时间未再上报的 firing 事件自动关闭（例如计划被删除后再无观测）。"""
    cutoff = utcnow() - timedelta(minutes=older_than_minutes)
    q = db.query(AlertEvent).filter(AlertEvent.status == "firing",
                                    AlertEvent.last_seen_at < cutoff)
    if tenant_id:
        q = q.filter(AlertEvent.tenant_id == tenant_id)
    n = 0
    for ev in q.all():
        ev.status = "resolved"
        ev.resolved_at = utcnow()
        n += 1
    if n:
        db.commit()
    return n
