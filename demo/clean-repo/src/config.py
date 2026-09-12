"""Runtime configuration for the clean demo app.

Secrets are read from the environment at startup; nothing is hardcoded.
"""
import os

DB_HOST = os.environ.get("APP_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("APP_DB_PORT", "5432"))
LOG_LEVEL = os.environ.get("APP_LOG_LEVEL", "INFO")


def database_url() -> str:
    password = os.environ.get("APP_DB_PASSWORD", "")
    return f"postgresql://{DB_HOST}:{DB_PORT}/app"
