"""数据模型。覆盖租户、CMDB 主机、任务、执行日志、巡检模板与计划。

多租户：除 Tenant 自身外，业务表均带 tenant_id，查询统一经 app.api.scope 过滤。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

# 单租户部署时使用的默认租户 id
DEFAULT_TENANT_ID = "default"


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    """租户（组织）。资源与用户均归属于某个租户。"""
    __tablename__ = "tenants"
    id = Column(String(32), primary_key=True, default=_uuid)
    code = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(String(255), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=_uuid)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False, default="")
    role = Column(String(16), default="operator")  # superadmin / admin / operator / viewer
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    # 平台级超管：可跨租户查看与管理（不受 tenant_id 限制）
    is_super = Column(Boolean, default=False)
    auth_source = Column(String(16), default="local")  # local / ldap / oidc
    display_name = Column(String(64), default="")
    email = Column(String(128), default="")
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)


class HostGroup(Base):
    __tablename__ = "host_groups"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(64), index=True, nullable=False)
    description = Column(String(255), default="")
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    hosts = relationship("Host", back_populates="group", cascade="all, delete-orphan")


class Host(Base):
    __tablename__ = "hosts"
    id = Column(String(32), primary_key=True, default=_uuid)
    hostname = Column(String(128), nullable=False)
    ip = Column(String(64), nullable=False)
    port = Column(Integer, default=22)
    os_type = Column(String(32), default="linux")  # linux / windows
    os_version = Column(String(64), default="")
    status = Column(String(16), default="unknown")  # online / offline / unknown
    tags = Column(JSON, default=list)
    group_id = Column(String(32), ForeignKey("host_groups.id"), nullable=True)
    credential_id = Column(String(32), ForeignKey("credentials.id"), nullable=True)
    # 探活结果（由 services/probe.py 刷新）
    last_seen = Column(DateTime, nullable=True)          # 最近一次探测成功时间
    probe_at = Column(DateTime, nullable=True)           # 最近一次探测时间（无论成败）
    probe_latency_ms = Column(Integer, nullable=True)    # 探测耗时，失败时为 None
    probe_message = Column(String(255), default="")      # 失败原因/成功摘要
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now)
    group = relationship("HostGroup", back_populates="hosts")
    credential = relationship("Credential", back_populates="hosts")


class Credential(Base):
    """SSH 凭据（密码/私钥加密存储）。"""
    __tablename__ = "credentials"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(64), nullable=False)
    type = Column(String(16), default="password")  # password / key
    username = Column(String(64), default="root")
    secret_encrypted = Column(Text, default="")    # 密码或私钥，加密后存储
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now)
    hosts = relationship("Host", back_populates="credential")


class AuditLog(Base):
    """审计日志：记录写操作（谁、何时、做了什么、结果）。"""
    __tablename__ = "audit_logs"
    id = Column(String(32), primary_key=True, default=_uuid)
    username = Column(String(64), default="")
    action = Column(String(32), default="")        # create/update/delete/execute/login
    resource = Column(String(64), default="")      # host/task/plan/credential/...
    resource_id = Column(String(32), default="")
    detail = Column(String(512), default="")
    ip = Column(String(64), default="")
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now, index=True)


class Task(Base):
    """一次作业/批量执行任务。"""
    __tablename__ = "tasks"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False)
    task_type = Column(String(16), default="adhoc")  # adhoc / playbook / inspection
    content = Column(Text, default="")          # adhoc 命令 或 playbook YAML
    target_type = Column(String(16), default="group")  # group / host
    target_id = Column(String(32), default="")
    status = Column(String(16), default="pending")  # pending/running/success/failed/partial
    summary = Column(JSON, default=dict)        # {ok, changed, failed, unreachable}
    created_by = Column(String(64), default="admin")
    # 产物归档地址（local 路径或 s3://bucket/key），由 artifact store 写入
    artifact_uri = Column(Text, default="")
    # 执行控制：失败重试次数、整体超时（秒，0=不限）、已尝试次数（含首次）
    max_retries = Column(Integer, default=0)
    timeout_seconds = Column(Integer, default=0)
    attempts = Column(Integer, default=0)
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")


class TaskLog(Base):
    __tablename__ = "task_logs"
    id = Column(String(32), primary_key=True, default=_uuid)
    task_id = Column(String(32), ForeignKey("tasks.id"), index=True, nullable=False)
    host = Column(String(128), default="")
    event = Column(String(32), default="")       # ok / changed / failed / unreachable / info
    message = Column(Text, default="")
    stdout = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    task = relationship("Task", back_populates="logs")


class InspectionTemplate(Base):
    """巡检模板（自然语言生成或手工创建）。"""
    __tablename__ = "inspection_templates"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False)
    description = Column(String(255), default="")
    category = Column(String(32), default="custom")  # mysql/redis/disk/cpu/mem/custom...
    playbook = Column(Text, default="")            # 生成/编写的 Playbook YAML
    generated_by_llm = Column(Boolean, default=False)
    status = Column(String(16), default="draft")    # draft / approved
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class InspectionPlan(Base):
    """巡检计划。"""
    __tablename__ = "inspection_plans"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False)
    template_id = Column(String(32), ForeignKey("inspection_templates.id"), nullable=True)
    target_type = Column(String(16), default="group")
    target_id = Column(String(32), default="")
    cron = Column(String(64), default="")          # cron 表达式
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now)


class InspectionReport(Base):
    """一次巡检执行产生的报告。"""
    __tablename__ = "inspection_reports"
    id = Column(String(32), primary_key=True, default=_uuid)
    plan_id = Column(String(32), nullable=True)     # 关联计划（手动执行可为空）
    plan_name = Column(String(128), default="")
    template_name = Column(String(128), default="")
    task_id = Column(String(32), nullable=True)     # 关联执行任务
    status = Column(String(16), default="success")  # success / partial / failed
    summary = Column(JSON, default=dict)
    content = Column(Text, default="")              # 报告正文/关键指标
    artifact_uri = Column(Text, default="")
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now, index=True)


class AlertConfig(Base):
    """告警通知配置（webhook）。"""
    __tablename__ = "alert_configs"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(64), default="")
    channel = Column(String(16), default="webhook")  # webhook / dingtalk / wecom
    webhook_url = Column(String(512), default="")
    enabled = Column(Boolean, default=True)
    # 只向该渠道推送 >= 此级别的告警：info < warning < critical
    min_severity = Column(String(16), default="info")
    # 未恢复的告警重复提醒间隔（分钟）；0 = 只在状态变化时提醒一次
    repeat_interval_minutes = Column(Integer, default=0)
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now)


class AlertEvent(Base):
    """告警事件（按 fingerprint 聚合的状态机）。

    firing -> resolved：同一资源连续异常只提醒一次，恢复时补一条恢复通知。
    fingerprint 例：plan:<计划id> / task:<任务id> / host:<主机id>
    """
    __tablename__ = "alert_events"
    id = Column(String(32), primary_key=True, default=_uuid)
    fingerprint = Column(String(128), unique=True, index=True, nullable=False)
    title = Column(String(255), default="")
    severity = Column(String(16), default="warning")   # info / warning / critical
    status = Column(String(16), default="firing")      # firing / resolved
    resource_type = Column(String(32), default="")     # plan / task / host
    resource_id = Column(String(32), default="")
    detail = Column(JSON, default=dict)
    occurrences = Column(Integer, default=1)
    first_seen_at = Column(DateTime, default=_now, index=True)
    last_seen_at = Column(DateTime, default=_now)
    last_notified_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)


class AlertSilence(Base):
    """告警静默窗口（维护期/变更期不让告警打扰）。

    scope 为空表示全局静默，否则为某资源 id（如巡检计划 id）。
    """
    __tablename__ = "alert_silences"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(128), default="")
    scope = Column(String(32), default="")            # "" = 全局；否则计划/主机 id
    starts_at = Column(DateTime, default=_now)
    ends_at = Column(DateTime, nullable=False)
    reason = Column(String(255), default="")
    created_by = Column(String(64), default="")
    tenant_id = Column(String(32), default=DEFAULT_TENANT_ID, index=True, nullable=False)
    created_at = Column(DateTime, default=_now)


class SchedulerLock(Base):
    """调度器选主租约。多实例部署时只有 leader 会注册并触发定时任务。"""
    __tablename__ = "scheduler_locks"
    name = Column(String(32), primary_key=True)      # 固定为 "scheduler"
    holder = Column(String(64), default="")          # 持有者实例 id
    acquired_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)


class PlanRun(Base):
    """计划执行去重表：同一计划的同一时间槽只允许执行一次（跨实例幂等）。"""
    __tablename__ = "plan_runs"
    id = Column(String(32), primary_key=True, default=_uuid)
    plan_id = Column(String(32), index=True, nullable=False)
    run_key = Column(String(128), unique=True, index=True, nullable=False)  # plan_id@slot
    instance_id = Column(String(64), default="")
    report_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_now, index=True)


Index("ix_task_logs_task_event", TaskLog.task_id, TaskLog.event)
