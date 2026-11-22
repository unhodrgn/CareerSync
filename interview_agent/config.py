"""Settings of the Interview Agent, from environment variables only (M5; docs/DECISIONS.md D52, D79).

The agent reads no `.env` file: the shell, Compose or the process manager sets its environment. The secret and the Groq key are never
logged or printed.

| Name | Default | Meaning |
|---|---|---|
| `INTERVIEW_AGENT_BACKEND_URL` | `http://localhost:8000` | Base URL of the backend's internal agent API |
| `INTERVIEW_AGENT_SECRET` | none (required) | The shared secret of the internal API, at least 32 characters (D79) |
| `AI_MODE` | `rules` | `rules`: no model call, the engine's rules for every turn; `llm`: Groq per turn (D52) |
| `GROQ_API_KEY` | none | Required in `llm` mode |
| `INTERVIEW_AGENT_LLM_MODEL` | `openai/gpt-oss-120b` | The Groq model (D52); a Claude model name is refused (the agent never calls Anthropic) |
| `INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS` | `3` | Per-turn model timeout; the rules decide at once after it (D79). Never above the session's limit |
| `INTERVIEW_AGENT_REASONING_EFFORT` | `low` for `openai/gpt-oss-*`, else none | Sent to Groq as `reasoning_effort` |
| `INTERVIEW_AGENT_DATA_DIR` | the repository's `data/` | Where `blocklist.yaml` and `interview_blocklist.yaml` are read |
"""
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_LLM_TIMEOUT_SECONDS = 3.0
SECRET_MIN_CHARS = 32  # the backend's INTERVIEW_AGENT_SECRET_MIN_CHARS


class ConfigError(ValueError):
    """A setting is missing or invalid. The message names the setting, never its value."""


@dataclass(frozen=True)
class AgentSettings:
    backend_url: str
    secret: str
    ai_mode: str
    groq_api_key: str
    llm_model: str
    llm_timeout: float
    reasoning_effort: str
    data_dir: Path

    @property
    def uses_model(self) -> bool:
        return self.ai_mode == "llm"


def _get(env: Mapping[str, str], name: str, default: str = "") -> str:
    value = env.get(name)
    return value.strip() if value is not None and value.strip() else default


def load_settings(env: Mapping[str, str] | None = None) -> AgentSettings:
    env = os.environ if env is None else env
    secret = _get(env, "INTERVIEW_AGENT_SECRET")
    if len(secret) < SECRET_MIN_CHARS:
        raise ConfigError(f"INTERVIEW_AGENT_SECRET must be set to at least {SECRET_MIN_CHARS} characters (the backend's value)")
    mode = _get(env, "AI_MODE", "rules").lower()
    if mode not in ("rules", "llm"):
        raise ConfigError("AI_MODE must be rules or llm")
    key = _get(env, "GROQ_API_KEY")
    if mode == "llm" and not key:
        raise ConfigError("AI_MODE=llm needs GROQ_API_KEY")
    model = _get(env, "INTERVIEW_AGENT_LLM_MODEL", DEFAULT_MODEL)
    if model.lower().startswith("claude"):
        raise ConfigError("INTERVIEW_AGENT_LLM_MODEL names a Claude model; the agent calls Groq only (D52)")
    try:
        timeout = float(_get(env, "INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS)))
    except ValueError as e:
        raise ConfigError("INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS must be a number of seconds") from e
    if not 0 < timeout <= 30:
        raise ConfigError("INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS must be above 0 and at most 30")
    effort = _get(env, "INTERVIEW_AGENT_REASONING_EFFORT", "low" if model.startswith("openai/gpt-oss") else "")
    if effort not in ("", "low", "medium", "high"):
        raise ConfigError("INTERVIEW_AGENT_REASONING_EFFORT must be low, medium or high")
    return AgentSettings(
        backend_url=_get(env, "INTERVIEW_AGENT_BACKEND_URL", "http://localhost:8000").rstrip("/"),
        secret=secret,
        ai_mode=mode,
        groq_api_key=key,
        llm_model=model,
        llm_timeout=timeout,
        reasoning_effort=effort,
        data_dir=Path(_get(env, "INTERVIEW_AGENT_DATA_DIR", str(REPO_ROOT / "data"))),
    )
