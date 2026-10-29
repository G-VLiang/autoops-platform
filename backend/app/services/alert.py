"""告警通知服务：任务/巡检异常时推送到 webhook（钉钉/企微/自定义）。"""
import logging
import httpx

logger = logging.getLogger("autoops.alert")

_CHANNEL_PAYLOAD = {
    "dingtalk": lambda text: {"msgtype": "text", "text": {"content": text}},
    "wecom": lambda text: {"msgtype": "text", "text": {"content": text}},
    "webhook": lambda text: {"text": text},
}


def _build_text(title: str, detail: dict) -> str:
    lines = [f"【AutoOps 告警】{title}"]
    for k, v in detail.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def send_alert(webhook_url: str, channel: str, title: str, detail: dict) -> bool:
    """发送告警，返回是否成功。占位实现：无 url 时仅记录日志。"""
    if not webhook_url:
        logger.info("[告警跳过] 未配置 webhook: %s %s", title, detail)
        return False

    text = _build_text(title, detail)
    payload = _CHANNEL_PAYLOAD.get(channel, _CHANNEL_PAYLOAD["webhook"])(text)
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("[告警成功] %s", title)
        return True
    except Exception as e:
        logger.error("[告警失败] %s: %s", title, e)
        return False


def notify_task_result(task, enabled_configs) -> None:
    """任务失败/部分失败时触发告警。"""
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
        send_alert(cfg.webhook_url, cfg.channel, f"任务异常: {task.name}", detail)
