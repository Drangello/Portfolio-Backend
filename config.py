import os

from dotenv import load_dotenv


load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


class Config:
    PRODUCTION = os.getenv("PORTFOLIO_ENV", "development") == "production"
    RATE_LIMIT_DB = os.getenv("RATE_LIMIT_DB", "/var/lib/portfolio-api/rate-limits.sqlite3")
    PRODUCTION_IP_LIMIT = 5
    PRODUCTION_GLOBAL_LIMIT = 30

    MAX_CONTENT_LENGTH = 24 * 1024

    CONTACT_RECIPIENT_EMAIL = os.getenv(
        "CONTACT_RECIPIENT_EMAIL",
        "florianweimann9@gmail.com",
    )
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = _get_int("SMTP_PORT", 587)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS", "")
    SMTP_TIMEOUT_SECONDS = _get_int("SMTP_TIMEOUT_SECONDS", 10)

    ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:4200")
    CONTACT_RATE_LIMIT = os.getenv("CONTACT_RATE_LIMIT", "5 per minute")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
