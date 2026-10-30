"""应用配置。所有敏感信息通过环境变量注入，提供本地开发默认值。"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AutoOps 运维自动化平台"
    API_PREFIX: str = "/api/v1"
    # 前端地址：SSO 回调后跳转用
    FRONTEND_URL: str = "http://localhost:5173"

    # 数据库（本地默认 SQLite，生产可切 PostgreSQL）
    DATABASE_URL: str = "sqlite:///./autoops.db"

    # 安全
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    # 凭据加密密钥（AES，需 32 字节；生产务必通过环境变量覆盖）
    CREDENTIAL_SECRET: str = "autoops-dev-aes-key-32-bytes!!!"

    # 执行引擎：mock / ansible
    EXECUTOR_BACKEND: str = "mock"

    # 大模型（OpenAI 兼容接口，留空则走 Mock）
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- 任务产物存储 ----
    # local：存本地磁盘；s3：任意 S3 兼容对象存储（AWS S3 / MinIO / 阿里云 OSS / 腾讯云 COS）
    ARTIFACT_BACKEND: str = "local"
    ARTIFACT_DIR: str = "./data/artifacts"
    ARTIFACT_S3_ENDPOINT: str = ""        # MinIO 等需要，如 http://127.0.0.1:9000
    ARTIFACT_S3_BUCKET: str = "autoops-artifacts"
    ARTIFACT_S3_ACCESS_KEY: str = ""
    ARTIFACT_S3_SECRET_KEY: str = ""
    ARTIFACT_S3_REGION: str = "us-east-1"
    ARTIFACT_PRESIGN_SECONDS: int = 3600
    # 本地产物保留天数（0 = 不清理）
    ARTIFACT_RETENTION_DAYS: int = 30

    # ---- 分布式调度 ----
    # 留空则自动生成（主机名-pid）；容器里建议显式设置成 pod 名
    INSTANCE_ID: str = ""
    # 允许本实例参与选主。单机部署保持 True；纯 worker/只读副本可设 False
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_LEASE_TTL: int = 30         # 租约有效期（秒）
    SCHEDULER_HEARTBEAT: int = 10         # 续约间隔（秒）

    # ---- 主机探活 ----
    # tcp：连 SSH 端口（推荐，云主机常禁 ping）；ping：ICMP
    PROBE_METHOD: str = "tcp"
    PROBE_TIMEOUT_SECONDS: float = 3.0
    PROBE_WORKERS: int = 32
    # 定时探活间隔（分钟），0 = 关闭定时探测（仍可手动点「立即探测」）
    HOST_PROBE_INTERVAL_MINUTES: int = 0

    # ---- 告警 ----
    # 告警事件自动关闭：超过该分钟数未再上报的 firing 事件视为失效（0 = 不自动关闭）
    ALERT_AUTO_RESOLVE_MINUTES: int = 0

    # ---- 任务执行 ----
    # 默认失败重试次数（任务创建时可覆盖），0 = 不重试
    TASK_DEFAULT_MAX_RETRIES: int = 0
    # 默认整体超时（秒），0 = 不限
    TASK_DEFAULT_TIMEOUT_SECONDS: int = 0

    # ---- LDAP ----
    LDAP_ENABLED: bool = False
    LDAP_SERVER: str = ""                  # ldap://dc.corp.local  或 ldaps://dc.corp.local:636
    LDAP_BASE_DN: str = "dc=corp,dc=local"
    LDAP_BIND_DN: str = ""                 # 服务账号，留空则直接用户 DN 绑定
    LDAP_BIND_PASSWORD: str = ""
    LDAP_USER_FILTER: str = "(sAMAccountName={username})"   # OpenLDAP 用 (uid={username})
    LDAP_USER_DN_TEMPLATE: str = ""        # 如 uid={username},ou=people,dc=corp,dc=local
    LDAP_ATTR_MAIL: str = "mail"
    LDAP_ATTR_DISPLAY: str = "displayName"
    LDAP_DEFAULT_ROLE: str = "operator"    # 首次登录自动开户的角色
    LDAP_DEFAULT_TENANT: str = "default"
    LDAP_USE_SSL: bool = False
    LDAP_TIMEOUT: int = 8

    # ---- OIDC / SSO ----
    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = ""                  # 如 https://login.microsoftonline.com/{tenant}/v2.0
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/oidc/callback"
    OIDC_SCOPES: str = "openid profile email"
    OIDC_DEFAULT_ROLE: str = "operator"
    OIDC_DEFAULT_TENANT: str = "default"
    # 角色映射：IdP 中的组/角色值 -> 平台角色，形如 admins:admin,ops:operator
    OIDC_ROLE_MAP: str = ""
    OIDC_DEFAULT_TENANT_FROM_CLAIM: str = ""   # 如 "tenant"，从 claim 取租户 code（需租户已存在）


settings = Settings()

BASE_DIR = Path(__file__).resolve().parent.parent
