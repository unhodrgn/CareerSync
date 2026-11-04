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

# Built-in secrets for local development only; the backend logs a warning at startup while one is in use
DEV_JWT_SECRET_KEY = "dev-only-secret-change-me-in-production-please"
DEV_TALENT_ID_SECRET = "dev-only-talent-id-secret-change-me-in-production"


def env_or_default(name: str, default: str) -> str:
    """The variable's value, or `default` when it is missing, empty or whitespace only (like Compose's
    `${VAR:-default}`). A value that is set is returned unchanged."""
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def _database_url() -> str:
    if url := env_or_default("DATABASE_URL", ""):
        return url
    user = env_or_default("DB_USER", "postgres")
    password = env_or_default("DB_PASSWORD", "postgres")
    host = env_or_default("DB_HOST", "localhost")
    port = env_or_default("DB_PORT", "5432")
    name = env_or_default("DB_NAME", "careersync_db")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


class Settings:
    DATABASE_URL: str = _database_url()
    JWT_SECRET_KEY: str = env_or_default("JWT_SECRET_KEY", DEV_JWT_SECRET_KEY)
    JWT_ALGORITHM: str = "HS256"
    # An invalid number still fails at startup; only missing or blank means the default
    JWT_EXPIRE_MINUTES: int = int(env_or_default("JWT_EXPIRE_MINUTES", "120"))
    # Key for the HMAC behind talent anonymous IDs; separate from JWT_SECRET_KEY so rotating one does not change the other
    TALENT_ID_SECRET: str = env_or_default("TALENT_ID_SECRET", DEV_TALENT_ID_SECRET)

    # Version of the consent text shown at registration; stored with each user
    CONSENT_VERSION: str = "2026-10-13"
    # First consent version whose AI-analysis purpose includes job recommendation (맞춤 추천);
    # users who consented to an older version get no recommendation (versions are ISO dates)
    RECO_MIN_CONSENT_VERSION: str = "2026-10-13"

    BLOCKLIST_PATH: Path = Path(env_or_default("BLOCKLIST_PATH", str(REPO_ROOT / "data" / "blocklist.yaml")))
    SKILLS_PATH: Path = Path(env_or_default("SKILLS_PATH", str(REPO_ROOT / "data" / "skills.yaml")))
    # Interview questions only, after the criteria guardrail (issue 30); data/blocklist.yaml stays unchanged
    INTERVIEW_BLOCKLIST_PATH: Path = Path(env_or_default("INTERVIEW_BLOCKLIST_PATH", str(REPO_ROOT / "data" / "interview_blocklist.yaml")))

    # Evaluation criteria
    CRITERIA_MAX_ITEMS: int = 10
    CRITERIA_WEIGHT_TOTAL: int = 100
    # Seeker-facing importance level, derived from weight: >= HIGH → 핵심, >= MID → 중요, else 일반 (D30)
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

    # Talent recommendation (docs/DECISIONS.md D19): evaluations one call may queue, always; and per company per
    # day (KST) only in AI_MODE=llm, counted generously (every evaluation of the company's jobs that no application references)
    TALENT_MAX_NEW_EVALUATIONS: int = 10
    TALENT_DAILY_NEW_EVALUATIONS: int = 30
    # Talent offers (docs/DECISIONS.md D20)
    OFFER_DAILY_LIMIT: int = 20  # per company per day (KST)
    OFFER_EXPIRY_DAYS: int = 14  # a pending offer older than this is expired

    # Career content (roadmap, interview questions; docs/DECISIONS.md D21): new LLM generations per seeker per day
    # (KST), only in AI_MODE=llm; cached content does not count. Over the limit the template is returned
    CAREER_DAILY_LLM_GENERATIONS: int = 10
    LEARNING_RESOURCES_PATH: Path = Path(env_or_default("LEARNING_RESOURCES_PATH", str(REPO_ROOT / "data" / "learning_resources.yaml")))

    # JD drafts (docs/DECISIONS.md D24): LLM drafts per company per day (KST), only in AI_MODE=llm. Counted in
    # process memory: reset on restart, correct only with one backend process (uvicorn without --workers)
    JD_DAILY_LLM_DRAFTS: int = 20


settings = Settings()


def dev_secrets_in_use() -> list[str]:
    """Names (never values) of the secrets still on their built-in dev value, for the startup warning."""
    secrets = (
        ("JWT_SECRET_KEY", settings.JWT_SECRET_KEY, DEV_JWT_SECRET_KEY),
        ("TALENT_ID_SECRET", settings.TALENT_ID_SECRET, DEV_TALENT_ID_SECRET),
    )
    return [name for name, value, dev in secrets if value == dev]
