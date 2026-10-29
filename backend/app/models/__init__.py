"""数据模型。覆盖 CMDB 主机、任务、执行日志、巡检模板与计划。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=_uuid)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    role = Column(String(16), default="admin")  # admin / operator / viewer
    created_at = Column(DateTime, default=_now)


class HostGroup(Base):
    __tablename__ = "host_groups"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(String(255), default="")
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
    created_at = Column(DateTime, default=_now)
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
    created_at = Column(DateTime, default=_now, index=True)


class AlertConfig(Base):
    """告警通知配置（webhook）。"""
    __tablename__ = "alert_configs"
    id = Column(String(32), primary_key=True, default=_uuid)
    name = Column(String(64), default="")
    channel = Column(String(16), default="webhook")  # webhook / dingtalk / wecom
    webhook_url = Column(String(512), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
