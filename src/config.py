"""
Configuration module for the Self-Healing Software System.
Handles environment variables and system-wide settings.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class AIConfig:
    """AI Provider Configuration"""
    provider: str  # 'groq' or 'cerebras'
    groq_api_key: Optional[str]
    cerebras_api_key: Optional[str]
    groq_base_url: str = "https://api.groq.com/openai/v1"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    cerebras_model: str = "llama3.1-8b"
    
    @property
    def active_api_key(self) -> str:
        """Get the API key for the active provider"""
        if self.provider == "groq":
            return self.groq_api_key or ""
        return self.cerebras_api_key or ""
    
    @property
    def active_base_url(self) -> str:
        """Get the base URL for the active provider"""
        if self.provider == "groq":
            return self.groq_base_url
        return self.cerebras_base_url
    
    @property
    def active_model(self) -> str:
        """Get the model for the active provider"""
        if self.provider == "groq":
            return self.groq_model
        return self.cerebras_model


@dataclass
class EmailConfig:
    """Email Configuration for notifications"""
    smtp_server: str
    smtp_port: int
    sender_email: str
    sender_password: str  # App password
    admin_email: str
    enable_notifications: bool = True


@dataclass
class GitConfig:
    """Git Configuration for version control operations"""
    repo_path: Path
    branch_prefix: str = "ai-fix"
    auto_commit: bool = True
    remote_name: str = "origin"


@dataclass
class SystemConfig:
    """Main System Configuration"""
    ai: AIConfig
    email: EmailConfig
    git: GitConfig
    log_file: Path
    target_service_path: Path
    max_fix_attempts: int = 5
    log_watch_interval: float = 1.0  # seconds
    test_timeout: int = 60  # seconds


def load_config() -> SystemConfig:
    """Load configuration from environment variables"""
    
    base_path = Path(__file__).parent.parent
    
    ai_config = AIConfig(
        provider=os.getenv("AI_PROVIDER", "groq"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        cerebras_model=os.getenv("CEREBRAS_MODEL", "llama3.1-8b"),
    )
    
    email_config = EmailConfig(
        smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        sender_email=os.getenv("SENDER_EMAIL", ""),
        sender_password=os.getenv("SENDER_PASSWORD", ""),  # App password
        admin_email=os.getenv("ADMIN_EMAIL", ""),
        enable_notifications=os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true",
    )
    
    git_config = GitConfig(
        repo_path=Path(os.getenv("GIT_REPO_PATH", str(base_path))),
        branch_prefix=os.getenv("GIT_BRANCH_PREFIX", "ai-fix"),
        auto_commit=os.getenv("GIT_AUTO_COMMIT", "true").lower() == "true",
        remote_name=os.getenv("GIT_REMOTE_NAME", "origin"),
    )
    
    return SystemConfig(
        ai=ai_config,
        email=email_config,
        git=git_config,
        log_file=Path(os.getenv("LOG_FILE", str(base_path / "logs" / "service.log"))),
        target_service_path=Path(os.getenv("TARGET_SERVICE_PATH", str(base_path / "demo_service"))),
        max_fix_attempts=int(os.getenv("MAX_FIX_ATTEMPTS", "5")),
        log_watch_interval=float(os.getenv("LOG_WATCH_INTERVAL", "1.0")),
        test_timeout=int(os.getenv("TEST_TIMEOUT", "60")),
    )


# Global config instance
config = load_config()
