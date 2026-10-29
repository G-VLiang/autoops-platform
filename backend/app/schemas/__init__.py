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
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Task ----
class TaskCreate(BaseModel):
    name: str
    task_type: str = "adhoc"
    content: str = ""
    target_type: str = "group"
    target_id: str = ""


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
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


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
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Alert Config ----
class AlertConfigCreate(BaseModel):
    name: str = ""
    channel: str = "webhook"
    webhook_url: str = ""
    enabled: bool = True


class AlertConfigOut(BaseModel):
    id: str
    name: str
    channel: str
    webhook_url: str
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


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
