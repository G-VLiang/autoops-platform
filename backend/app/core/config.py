"""应用配置。所有敏感信息通过环境变量注入，提供本地开发默认值。"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AutoOps 运维自动化平台"
    API_PREFIX: str = "/api/v1"

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


settings = Settings()

BASE_DIR = Path(__file__).resolve().parent.parent
