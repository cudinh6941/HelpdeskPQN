from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ROOT_ENV = BASE_DIR.parent / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "IT Helpdesk System"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./helpdesk_dev.db"

    # Corporate LDAP / Active Directory Authentication
    LDAP_ENABLED: bool = False
    LDAP_ALLOW_LOCAL_FALLBACK: bool = True
    LDAP_SERVER_URI: str = "ldap://dc.company.local:389"
    LDAP_USE_SSL: bool = False
    LDAP_DOMAIN: str = "COMPANY"
    LDAP_BASE_DN: str = "DC=company,DC=local"
    LDAP_USER_DN_TEMPLATE: str = "{username}@company.local"
    LDAP_SEARCH_FILTER: str = "(sAMAccountName={username})"
    LDAP_BIND_TIMEOUT_SECONDS: int = 5
    LDAP_ADMIN_GROUP: str = "Helpdesk_Admins"
    LDAP_LEAD_GROUP: str = "IT_Leads"
    LDAP_AGENT_GROUP: str = "IT_Agents"

    # JWT Authentication
    JWT_SECRET_KEY: str = "dev-secret-key-helpdesk-pqn-2026-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # MinIO Object Storage
    MINIO_ENABLED: bool = False
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin123"
    MINIO_INTERNAL_ENDPOINT: str = "localhost:9000"
    MINIO_PUBLIC_ENDPOINT: str = "localhost:9000"
    MINIO_BUCKET: str = "helpdesk-attachments"
    MINIO_USE_SSL: bool = False
    LOCAL_STORAGE_DIR: str = str(BASE_DIR / "storage_data")

    # Transactional Outbox & n8n Webhook
    N8N_WEBHOOK_URL: str = "http://localhost:5678/webhook/it-helpdesk"
    N8N_WEBHOOK_SECRET: str = "helpdesk-n8n-secret"
    N8N_DRY_RUN: bool = True
    RUN_EMBEDDED_WORKERS: bool = True
    OUTBOX_POLL_INTERVAL_SECONDS: int = 5
    SLA_SCAN_INTERVAL_SECONDS: int = 30

    # Automation (Smart Auto-Assign & Auto-Close)
    AUTO_ASSIGN_ENABLED: bool = True
    AUTO_CLOSE_RESOLVED_HOURS: int = 48

    # Attachments & Security
    ATTACHMENT_MAX_BYTES: int = 10 * 1024 * 1024
    ORPHAN_ATTACHMENT_MAX_AGE_HOURS: int = 24
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_LOCKOUT_SECONDS: int = 300

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=[str(ROOT_ENV), ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
