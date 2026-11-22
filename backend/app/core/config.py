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

    # Practice interview (docs/DECISIONS.md D57): reservations per seeker per KST day, kept in the database ledger
    # (`interview_quota`). A reservation is never refunded, and deleting a session does not give one back
    INTERVIEW_DAILY_SESSIONS: int = 3
    INTERVIEW_DAILY_PLAN_MODEL_CALLS: int = 3
    INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS: int = 3

    # Practice interview lifecycle (docs/DECISIONS.md D53, D57). Constants, not environment variables
    # Version of the transcript-storage consent text (interview_consent_service); a changed text needs a new version
    INTERVIEW_CONSENT_VERSION: str = "2026-11-16"
    INTERVIEW_RETENTION_DAYS: int = 30  # expires_at = created_at + this; never extended
    INTERVIEW_JOIN_SECONDS: int = 300  # a created session can be joined for this long after its plan is ready
    INTERVIEW_MAX_SECONDS: int = 600  # time budget of a live session, counted from its start
    # After INTERVIEW_MAX_SECONDS only the final end event and the closing agent line are accepted, for this long
    INTERVIEW_END_GRACE_SECONDS: int = 30
    INTERVIEW_PLAN_LEASE_SECONDS: int = 120  # a planning session must be finished within this (the model call included)
    # Feedback (M4 S3b, D64): a feedback-model attempt holds the session's lease for this long (a normal call ends in about 90 s, see
    # ai/llm/client.py), and a session gets at most this many model attempts, a failed or crashed one included
    INTERVIEW_FEEDBACK_LEASE_SECONDS: int = 120
    INTERVIEW_FEEDBACK_MAX_ATTEMPTS: int = 3
    # The limits the engine runs with (D57); each session stores the ones it started with
    INTERVIEW_MAX_QUESTIONS: int = 5
    INTERVIEW_MAX_FOLLOWUPS_PER_ITEM: int = 2
    INTERVIEW_MAX_CLARIFIES_PER_ITEM: int = 1
    INTERVIEW_SILENCE_NUDGE_SECONDS: int = 20
    INTERVIEW_SILENCE_SKIP_SECONDS: int = 45
    INTERVIEW_TURN_LLM_DEADLINE_SECONDS: int = 8
    # Retention maintenance on create and list: expired sessions removed per call, and the page size of the history
    INTERVIEW_LAZY_PURGE_BATCH: int = 50
    INTERVIEW_HISTORY_DEFAULT_LIMIT: int = 20
    INTERVIEW_HISTORY_MAX_LIMIT: int = 50
    # Ingestion of turns (M4 S3a). Regular turns take sequence numbers 1 to MAX_TURNS - 1; the closing line may take MAX_TURNS
    INTERVIEW_MAX_TURNS: int = 120
    INTERVIEW_MAX_TURN_CHARS: int = 4000  # of a stored (masked) turn: the same limit as the CHECK on interview_turns.text
    INTERVIEW_MAX_RAW_TURN_CHARS: int = 8000  # of a text as received, before masking; over it is refused, never cut
    INTERVIEW_COVERAGE_MAX_BYTES: int = 4096  # of a validated coverage snapshot as stored
    # Interview Agent (M5, docs/DECISIONS.md D58, D79): the shared secret of the internal agent API. Unset, or shorter than the
    # minimum, refuses every internal call (fail closed). Never logged or returned
    INTERVIEW_AGENT_SECRET: str = env_or_default("INTERVIEW_AGENT_SECRET", "")
    INTERVIEW_AGENT_SECRET_MIN_CHARS: int = 32


settings = Settings()


def dev_secrets_in_use() -> list[str]:
    """Names (never values) of the secrets still on their built-in dev value, for the startup warning."""
    secrets = (
        ("JWT_SECRET_KEY", settings.JWT_SECRET_KEY, DEV_JWT_SECRET_KEY),
        ("TALENT_ID_SECRET", settings.TALENT_ID_SECRET, DEV_TALENT_ID_SECRET),
    )
    return [name for name, value, dev in secrets if value == dev]
