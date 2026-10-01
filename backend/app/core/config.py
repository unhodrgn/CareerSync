"""App settings, read from environment variables (see README for the .env keys)."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _database_url() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    host = os.getenv("DB_HOST", "localhost")
    name = os.getenv("DB_NAME", "careersync_db")
    return f"postgresql+psycopg://{user}:{password}@{host}/{name}"


class Settings:
    DATABASE_URL: str = _database_url()
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-only-secret-change-me-in-production-please")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

    BLOCKLIST_PATH: Path = Path(os.getenv("BLOCKLIST_PATH", REPO_ROOT / "data" / "blocklist.yaml"))

    # Evaluation criteria
    CRITERIA_MAX_ITEMS: int = 10
    CRITERIA_WEIGHT_TOTAL: int = 100
    # Seeker-facing importance level, derived from weight: >= HIGH → 높음, >= MID → 보통, else 낮음
    IMPORTANCE_HIGH: int = 25
    IMPORTANCE_MID: int = 10


settings = Settings()
