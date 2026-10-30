"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ---- Auth ----
class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str = ""
    role: str = ""
    tenant_id: str = ""
    tenant_name: str = ""
    is_super: bool = False
    display_name: str = ""
    auth_source: str = "local"


class MeOut(BaseModel):
    username: str
    role: str
    is_super: bool = False
    display_name: str = ""
    email: str = ""
    auth_source: str = "local"
    tenant_id: str = ""
    tenant_name: str = ""
    tenant_code: str = ""
    last_login_at: Optional[datetime] = None


# ---- Tenant ----
class TenantCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str
    description: str = ""
    enabled: bool = True


class TenantOut(BaseModel):
    id: str
    code: str
    name: str
    description: str = ""
    enabled: bool = True
    created_at: datetime
    user_count: int = 0
    host_count: int = 0

    class Config:
        from_attributes = True


# ---- Host Group ----
class HostGroupCreate(BaseModel):
    name: str
    description: str = ""


class HostGroupOut(BaseModel):
    id: str
    name: str
    description: str
    host_count: int = 0

    class Config:
        from_attributes = True


# ---- Host ----
class HostCreate(BaseModel):
    hostname: str
    ip: str
    port: int = 22
    os_type: str = "linux"
    os_version: str = ""
    group_id: Optional[str] = None
    tags: List[str] = []


class HostOut(BaseModel):
    id: str
    hostname: str
    ip: str
    port: int
    os_type: str
    os_version: str
    status: str
    tags: List[str]
    group_id: Optional[str]
    group_name: Optional[str] = None
    last_seen: Optional[datetime] = None
    probe_at: Optional[datetime] = None
    probe_latency_ms: Optional[int] = None
    probe_message: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Host Probe ----
class ProbeRequest(BaseModel):
    host_ids: List[str] = []      # 为空则探测当前租户全部主机
    port: Optional[int] = None    # 不填则用主机自身 ssh 端口


class ProbeItem(BaseModel):
    host_id: str
    hostname: str
    ip: str
    online: bool
    latency_ms: Optional[int] = None
    message: str = ""


class ProbeSummary(BaseModel):
    total: int
    online: int
    offline: int
    elapsed_ms: int
    results: List[ProbeItem] = []


# ---- Task ----
class TaskCreate(BaseModel):
    name: str
    task_type: str = "adhoc"
    content: str = ""
    target_type: str = "group"
    target_id: str = ""
    max_retries: int = 0          # 失败后重试次数（0 = 不重试）
    timeout_seconds: int = 0      # 整体执行超时，0 = 不限


class TaskOut(BaseModel):
    id: str
    name: str
    task_type: str
    content: str
    target_type: str
    target_id: str
    status: str
    summary: dict
    created_by: str
    artifact_uri: str = ""
    max_retries: int = 0
    timeout_seconds: int = 0
    attempts: int = 0
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class LibraryItem(BaseModel):
    """预置作业模板。"""
    key: str
    name: str
    category: str
    description: str
    task_type: str = "playbook"
    content: str
    tags: List[str] = []


class TaskFromLibrary(BaseModel):
    library_key: str
    name: str = ""            # 留空则用模板名
    target_type: str = "group"
    target_id: str
    max_retries: int = 0
    timeout_seconds: int = 0


class TaskLogOut(BaseModel):
    id: str
    host: str
    event: str
    message: str
    stdout: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Inspection Template ----
class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "custom"
    playbook: str = ""
    generated_by_llm: bool = False
    status: str = "draft"


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    category: str
    playbook: str
    generated_by_llm: bool
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- LLM ----
class NL2PlaybookRequest(BaseModel):
    prompt: str
    category: str = "custom"
    target_group_id: Optional[str] = None


class NL2PlaybookResponse(BaseModel):
    name: str
    description: str
    category: str
    playbook: str
    generated_by_llm: bool
    is_mock: bool


# ---- Inspection Plan ----
class PlanCreate(BaseModel):
    name: str
    template_id: Optional[str] = None
    target_type: str = "group"
    target_id: str = ""
    cron: str = "daily"
    enabled: bool = True


class PlanOut(BaseModel):
    id: str
    name: str
    template_id: Optional[str]
    template_name: Optional[str] = None
    target_type: str
    target_id: str
    cron: str
    enabled: bool
    last_run_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Inspection Report ----
class ReportOut(BaseModel):
    id: str
    plan_id: Optional[str]
    plan_name: str
    template_name: str
    task_id: Optional[str]
    status: str
    summary: dict
    content: str
    artifact_uri: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Alert Config ----
class AlertConfigCreate(BaseModel):
    name: str = ""
    channel: str = "webhook"
    webhook_url: str = ""
    enabled: bool = True
    min_severity: str = "info"              # 只推 >= 该级别
    repeat_interval_minutes: int = 0        # 未恢复重复提醒间隔，0 = 只在状态变化时提醒


class AlertConfigOut(BaseModel):
    id: str
    name: str
    channel: str
    webhook_url: str
    enabled: bool
    min_severity: str = "info"
    repeat_interval_minutes: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class AlertEventOut(BaseModel):
    id: str
    fingerprint: str
    title: str
    severity: str
    status: str
    resource_type: str
    resource_id: str
    detail: dict
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    last_notified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertSilenceCreate(BaseModel):
    name: str = ""
    scope: str = ""            # "" = 全局静默；否则为计划/主机 id
    minutes: int = Field(default=60, ge=1, le=60 * 24 * 30)
    reason: str = ""


class AlertSilenceOut(BaseModel):
    id: str
    name: str
    scope: str
    starts_at: datetime
    ends_at: datetime
    reason: str
    created_by: str
    active: bool = True

    class Config:
        from_attributes = True


# ---- Cron ----
class CronPreviewRequest(BaseModel):
    cron: str
    count: int = 5


class CronPreviewResponse(BaseModel):
    valid: bool
    expression: str = ""
    description: str = ""
    next_runs: List[datetime] = []
    error: str = ""


# ---- Credential ----
class CredentialCreate(BaseModel):
    name: str
    type: str = "password"
    username: str = "root"
    secret: str = ""        # 明文密码或私钥（仅创建时传入）


class CredentialOut(BaseModel):
    id: str
    name: str
    type: str
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Audit ----
class AuditOut(BaseModel):
    id: str
    username: str
    action: str
    resource: str
    resource_id: str
    detail: str
    ip: str
    created_at: datetime

    class Config:
        from_attributes = True
