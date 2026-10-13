"""App settings, read from environment variables (see PROJECT_DOCUMENTATION.md §9 for the .env keys).

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
    CONSENT_VERSION: str = "2026-10-13"
    # First consent version whose AI-analysis purpose includes job recommendation (맞춤 추천);
    # users who consented to an older version get no recommendation (versions are ISO dates)
    RECO_MIN_CONSENT_VERSION: str = "2026-10-13"

    BLOCKLIST_PATH: Path = Path(os.getenv("BLOCKLIST_PATH", REPO_ROOT / "data" / "blocklist.yaml"))
    SKILLS_PATH: Path = Path(os.getenv("SKILLS_PATH", REPO_ROOT / "data" / "skills.yaml"))

    # Evaluation criteria
    CRITERIA_MAX_ITEMS: int = 10
    CRITERIA_WEIGHT_TOTAL: int = 100
    # Seeker-facing importance level, derived from weight: >= HIGH → 높음, >= MID → 보통, else 낮음
    IMPORTANCE_HIGH: int = 25
    IMPORTANCE_MID: int = 10

    # A pending evaluation queued longer ago than this is treated as dead (e.g. server restart) and may be re-queued
    EVALUATION_STALE_MINUTES: int = 10
    # Automatic queues by recommendation per evaluation; apply and 다시 분석 are not limited
    EVALUATION_MAX_ATTEMPTS: int = 3

    # Job recommendation (docs/DECISIONS.md D2, D16): Final = FIT_WEIGHT·Fit + PREF_WEIGHT·Pref
    RECO_FIT_WEIGHT: float = 0.5
    RECO_PREF_WEIGHT: float = 0.5
    RECO_MIN_FIT: float = 40
    RECO_MIN_PREF: float = 40
    # Seeker-facing band from Final: >= HIGH → 매우 적합, >= MID → 적합, else 참고
    RECO_BAND_HIGH: float = 80
    RECO_BAND_MID: float = 60
    # Evaluations one call may queue (new or re-queued), always
    RECO_MAX_NEW_EVALUATIONS: int = 10
    # Per seeker per day (KST), only in AI_MODE=llm, where scoring costs money
    RECO_DAILY_NEW_EVALUATIONS: int = 30


settings = Settings()
