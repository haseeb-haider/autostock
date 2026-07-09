"""Central configuration, all overridable via environment variables."""
import os


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --- Database -------------------------------------------------------------
# Neon / Render give a postgres URL. Locally we fall back to SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./autostock.db")

# --- Security -------------------------------------------------------------
# Token that protects the automation + webhook endpoints.
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "change-me")
# Optional HTTP Basic auth over the whole UI (leave blank to disable).
APP_USER = os.environ.get("APP_USER", "")
APP_PASS = os.environ.get("APP_PASS", "")

# --- Email (SMTP) ---------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER or "autostock@localhost")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", SMTP_USER or "")

# --- Automation behaviour -------------------------------------------------
# How many days of sales history define the "recent consumption rate".
WINDOW_DAYS = _int("WINDOW_DAYS", 30)
# Default supplier lead time if a supplier has none set.
DEFAULT_LEAD_DAYS = _int("DEFAULT_LEAD_DAYS", 7)
# Extra safety buffer added on top of lead time when sizing reorder points.
SAFETY_DAYS = _int("SAFETY_DAYS", 3)
# When reordering, buy enough to cover this many days beyond lead time.
COVER_DAYS = _int("COVER_DAYS", 30)
# If true, the daily job creates Purchase rows (status "ordered") automatically.
AUTO_CREATE_PO = _bool("AUTO_CREATE_PO", False)
# If true, drafted POs are emailed to each supplier. If false, a digest goes to ALERT_EMAIL.
AUTO_SEND_PO = _bool("AUTO_SEND_PO", False)
# Run APScheduler inside the web process. Off by default; use the GitHub Action instead.
ENABLE_SCHEDULER = _bool("ENABLE_SCHEDULER", False)
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "AutoStock")
