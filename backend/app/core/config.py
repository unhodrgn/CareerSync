"""App settings, read from environment variables (see README for the .env keys).

The repo-root `.env` is loaded first, so local runs need no `$env:...` per terminal. Variables
already set in the shell win over `.env`. Tests set CAREERSYNC_DOTENV=0 to skip the file.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

if os.getenv("CAREERSYNC_DOTENV", "1") != "0":
    load_dotenv(REPO_ROOT / ".env", override=False)


def _database_url() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "careersync_db")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


class Settings:
    DATABASE_URL: str = _database_url()
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-only-secret-change-me-in-production-please")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

    # Version of the consent text shown at registration; stored with each user
    CONSENT_VERSION: str = "2026-10-01"

    BLOCKLIST_PATH: Path = Path(os.getenv("BLOCKLIST_PATH", REPO_ROOT / "data" / "blocklist.yaml"))
    SKILLS_PATH: Path = Path(os.getenv("SKILLS_PATH", REPO_ROOT / "data" / "skills.yaml"))

    # Evaluation criteria
    CRITERIA_MAX_ITEMS: int = 10
    CRITERIA_WEIGHT_TOTAL: int = 100
    # Seeker-facing importance level, derived from weight: >= HIGH → 높음, >= MID → 보통, else 낮음
    IMPORTANCE_HIGH: int = 25
    IMPORTANCE_MID: int = 10


settings = Settings()
