import os
from dataclasses import dataclass


def _bool_env(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    app_name: str = os.environ.get("APP_NAME", "98Mail")
    imap_host: str = os.environ.get("IMAP_HOST", "127.0.0.1")
    imap_port: int = int(os.environ.get("IMAP_PORT", "993"))
    imap_use_ssl: bool = _bool_env("IMAP_USE_SSL", "true")
    smtp_host: str = os.environ.get("SMTP_HOST", "127.0.0.1")
    smtp_port: int = int(os.environ.get("SMTP_PORT", "587"))
    session_secure: bool = _bool_env("SESSION_SECURE", "true")
    session_max_age: int = int(os.environ.get("SESSION_MAX_AGE", "86400"))


config = Config()
