"""
Configuration module for the Self-Healing Software System v2.0
WebSocket-based log streaming, AST analysis, and code review system.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class AIConfig(BaseModel):
    """AI Provider Configuration"""
    provider: str = "groq"  # 'groq', 'cerebras', or 'azure'
    groq_api_key: Optional[str] = None
    cerebras_api_key: Optional[str] = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    cerebras_model: str = "llama-3.3-70b"
    # Azure OpenAI
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_api_version: str = "2024-12-01-preview"
    max_retries: int = 5
    initial_retry_delay: float = 2.0
    max_tokens: int = 8192
    
    @property
    def active_api_key(self) -> str:
        """Get the API key for the active provider"""
        if self.provider == "azure":
            return self.azure_openai_api_key or ""
        if self.provider == "groq":
            return self.groq_api_key or ""
        return self.cerebras_api_key or ""
    
    @property
    def active_base_url(self) -> str:
        """Get the base URL for the active provider"""
        if self.provider == "azure":
            ep = (self.azure_openai_endpoint or "").rstrip("/")
            return f"{ep}/openai/deployments/{self.azure_openai_deployment}"
        if self.provider == "groq":
            return self.groq_base_url
        return self.cerebras_base_url
    
    @property
    def active_model(self) -> str:
        """Get the model for the active provider"""
        if self.provider == "azure":
            return self.azure_openai_deployment
        if self.provider == "groq":
            return self.groq_model
        return self.cerebras_model


class DatabaseConfig(BaseModel):
    """PostgreSQL Database Configuration"""
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    database: str = "selfhealer"
    min_connections: int = 5
    max_connections: int = 20
    encryption_key: str = "change-this-encryption-key-in-production"
    ssl: bool = False


class RedisConfig(BaseModel):
    """Redis Configuration"""
    host: str = "localhost"
    port: int = 6379
    password: Optional[str] = None
    db: int = 0
    max_connections: int = 50


class EmailConfig(BaseModel):
    """Email Configuration for notifications"""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = ""
    sender_password: str = ""  # App password
    admin_email: str = ""
    enable_notifications: bool = True


class GitHubConfig(BaseModel):
    """GitHub/GitLab Configuration for repository access"""
    default_token: Optional[str] = None
    repos_base_path: Path = Field(default_factory=lambda: Path("repos"))
    pull_interval_minutes: int = 5  # How often to git pull
    pr_webhook_secret: Optional[str] = None


class ServerConfig(BaseModel):
    """Server Configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    websocket_path: str = "/ws/logs"
    api_prefix: str = "/api/v1"
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    jwt_secret: str = "change-this-jwt-secret-in-production"
    jwt_expiry_hours: int = 24


class StorageConfig(BaseModel):
    """Storage Configuration for user tiers"""
    free_max_repos: int = 5
    free_max_storage_per_repo_mb: int = 100
    pro_max_repos: int = 999999  # Unlimited
    pro_max_storage_per_repo_mb: int = 1024  # 1 GB


class RateLimitConfig(BaseModel):
    """Rate Limiting Configuration"""
    logs_per_second: int = 100
    prs_per_hour: int = 10
    api_calls_per_minute: int = 60


class SystemConfig(BaseModel):
    """Main System Configuration"""
    ai: AIConfig = Field(default_factory=AIConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    base_path: Path = Field(default_factory=lambda: Path(__file__).parent.parent)
    logs_path: Path = Field(default_factory=lambda: Path("logs"))
    temp_path: Path = Field(default_factory=lambda: Path("temp"))
    
    class Config:
        arbitrary_types_allowed = True


def load_config() -> SystemConfig:
    """Load configuration from environment variables"""
    
    base_path = Path(__file__).parent.parent
    
    ai_config = AIConfig(
        provider=os.getenv("AI_PROVIDER", "groq"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        cerebras_model=os.getenv("CEREBRAS_MODEL", "llama3.1-8b"),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        azure_api_version=os.getenv("API_VERSION", "2024-12-01-preview"),
        max_retries=int(os.getenv("AI_MAX_RETRIES", "5")),
        initial_retry_delay=float(os.getenv("AI_INITIAL_RETRY_DELAY", "2.0")),
        max_tokens=int(os.getenv("AI_MAX_TOKENS", "8192")),
    )
    
    database_config = DatabaseConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "selfhealer"),
        min_connections=int(os.getenv("DB_MIN_CONNECTIONS", "5")),
        max_connections=int(os.getenv("DB_MAX_CONNECTIONS", "20")),
        encryption_key=os.getenv("DB_ENCRYPTION_KEY", "change-this-encryption-key-in-production"),
        ssl=os.getenv("DB_SSL", "false").lower() == "true",
    )
    
    redis_config = RedisConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=int(os.getenv("REDIS_DB", "0")),
        max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
    )
    
    email_config = EmailConfig(
        smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        sender_email=os.getenv("SENDER_EMAIL", ""),
        sender_password=os.getenv("SENDER_PASSWORD", ""),
        admin_email=os.getenv("ADMIN_EMAIL", ""),
        enable_notifications=os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "true").lower() == "true",
    )
    
    github_config = GitHubConfig(
        default_token=os.getenv("GITHUB_TOKEN"),
        repos_base_path=base_path / "repos",
        pull_interval_minutes=int(os.getenv("GIT_PULL_INTERVAL", "5")),
        pr_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET"),
    )
    
    server_config = ServerConfig(
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
        websocket_path=os.getenv("WEBSOCKET_PATH", "/ws/logs"),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        jwt_secret=os.getenv("JWT_SECRET", "change-this-jwt-secret-in-production"),
        jwt_expiry_hours=int(os.getenv("JWT_EXPIRY_HOURS", "24")),
    )
    
    storage_config = StorageConfig(
        free_max_repos=int(os.getenv("FREE_MAX_REPOS", "5")),
        free_max_storage_per_repo_mb=int(os.getenv("FREE_MAX_STORAGE_MB", "100")),
        pro_max_repos=int(os.getenv("PRO_MAX_REPOS", "999999")),
        pro_max_storage_per_repo_mb=int(os.getenv("PRO_MAX_STORAGE_MB", "1024")),
    )
    
    rate_limit_config = RateLimitConfig(
        logs_per_second=int(os.getenv("RATE_LIMIT_LOGS_PER_SEC", "100")),
        prs_per_hour=int(os.getenv("RATE_LIMIT_PRS_PER_HOUR", "10")),
        api_calls_per_minute=int(os.getenv("RATE_LIMIT_API_PER_MIN", "60")),
    )
    
    return SystemConfig(
        ai=ai_config,
        database=database_config,
        redis=redis_config,
        email=email_config,
        github=github_config,
        server=server_config,
        storage=storage_config,
        rate_limits=rate_limit_config,
        base_path=base_path,
        logs_path=base_path / "logs",
        temp_path=base_path / "temp",
    )


# Global config instance
_config: Optional[SystemConfig] = None


def get_config() -> SystemConfig:
    """Get or create the global config instance"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


# Convenience export
config = get_config()
