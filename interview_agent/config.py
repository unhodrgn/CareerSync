"""Settings of the Interview Agent, from environment variables only (M5; docs/DECISIONS.md D52, D80).

The agent reads no `.env` file: the shell, Compose or the process manager sets its environment. The secret and the Groq key are never
logged or printed.

| Name | Default | Meaning |
|---|---|---|
| `INTERVIEW_AGENT_BACKEND_URL` | `http://localhost:8000` | Base URL of the backend's internal agent API |
| `INTERVIEW_AGENT_SECRET` | none (required) | The shared secret of the internal API, at least 32 characters (D80) |
| `AI_MODE` | `rules` | `rules`: no model call, the engine's rules for every turn; `llm`: Groq per turn (D52) |
| `GROQ_API_KEY` | none | Required in `llm` mode |
| `INTERVIEW_AGENT_LLM_MODEL` | `openai/gpt-oss-120b` | The Groq model (D52); a Claude model name is refused (the agent never calls Anthropic) |
| `INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS` | `3` | Per-turn model timeout; the rules decide at once after it (D80). Never above the session's limit |
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


# ── The voice worker (M5 S4) ──
#
# More variables, read only by `voice.py`. LiveKit's own variables (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`) are read by the
# SDK itself: to register the worker, and by LiveKit Inference (speech recognition, speech synthesis, the turn detector), which signs with
# the same key and secret. They are checked here only for being present, and never printed.
#
# | Name | Default | Meaning |
# |---|---|---|
# | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | none (required) | The LiveKit Cloud project |
# | `INTERVIEW_AGENT_NAME` | `careersync-interviewer` | The agent name the worker registers under; the backend's join token dispatches this name |
# | `INTERVIEW_AGENT_STT_MODEL` | `deepgram/nova-3` | LiveKit Inference speech recognition model (Korean is listed for it) |
# | `INTERVIEW_AGENT_TTS_MODEL` | `cartesia/sonic-3` | LiveKit Inference speech synthesis model (Korean is listed for it) |
# | `INTERVIEW_AGENT_TTS_VOICE` | a Cartesia sample voice | The voice id; listen to the Korean output and change it if it sounds wrong |
# | `INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS` | `3.0` | Wait after the candidate's last speech when the turn detector thinks the sentence is complete |
# | `INTERVIEW_AGENT_ENDPOINT_MAX_SECONDS` | `6.0` | Wait when it thinks the candidate is not done; the turn ends after this whatever it says |
# | `INTERVIEW_AGENT_STATUS_POLL_SECONDS` | `5` | How often the worker asks the backend whether the session is still active (D80) |
# | `INTERVIEW_AGENT_CONSOLE_SESSION_ID` | none | `console` mode only: the session to run (a console job carries no metadata) |
DEFAULT_AGENT_NAME = "careersync-interviewer"  # the default of the backend's INTERVIEW_AGENT_NAME; a backend test checks that they agree
DEFAULT_STT_MODEL = "deepgram/nova-3"
DEFAULT_TTS_MODEL = "cartesia/sonic-3"
# The sample voice of LiveKit's Cartesia page. It documents no Korean voice: the voice is checked by listening in the live run
DEFAULT_TTS_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
LANGUAGE = "ko"
TURN_DETECTOR_VERSION = "v1"  # the full model, served by LiveKit Inference; without a version `start` would run the local v1-mini
LIVEKIT_VARIABLES = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")


@dataclass(frozen=True)
class VoiceSettings:
    agent: AgentSettings
    agent_name: str
    stt_model: str
    tts_model: str
    tts_voice: str
    language: str
    endpoint_min: float
    endpoint_max: float
    status_poll: float
    console_session_id: int | None


def agent_name_from_env(env: Mapping[str, str] | None = None) -> str:
    """Read at import time by `voice.py`, which needs the name to register the worker."""
    return _get(os.environ if env is None else env, "INTERVIEW_AGENT_NAME", DEFAULT_AGENT_NAME)


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(_get(env, name, str(default)))
    except ValueError as e:
        raise ConfigError(f"{name} must be a number of seconds") from e
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low:g} and {high:g}")
    return value


def load_voice_settings(env: Mapping[str, str] | None = None) -> VoiceSettings:
    env = os.environ if env is None else env
    missing = [name for name in LIVEKIT_VARIABLES if not _get(env, name)]
    if missing:
        raise ConfigError("the voice worker needs " + ", ".join(missing) + " (the LiveKit Cloud project)")
    agent = load_settings(env)
    low = _number(env, "INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS", 3.0, 0.3, 10.0)
    high = _number(env, "INTERVIEW_AGENT_ENDPOINT_MAX_SECONDS", 6.0, 0.3, 15.0)
    if high < low:
        raise ConfigError("INTERVIEW_AGENT_ENDPOINT_MAX_SECONDS must not be below INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS")
    console = _get(env, "INTERVIEW_AGENT_CONSOLE_SESSION_ID")
    if console and not (console.isdigit() and 0 < int(console) < 2**31):
        raise ConfigError("INTERVIEW_AGENT_CONSOLE_SESSION_ID must be a session id (a positive integer)")
    return VoiceSettings(
        agent=agent,
        agent_name=agent_name_from_env(env),
        stt_model=_get(env, "INTERVIEW_AGENT_STT_MODEL", DEFAULT_STT_MODEL),
        tts_model=_get(env, "INTERVIEW_AGENT_TTS_MODEL", DEFAULT_TTS_MODEL),
        tts_voice=_get(env, "INTERVIEW_AGENT_TTS_VOICE", DEFAULT_TTS_VOICE),
        language=LANGUAGE,
        endpoint_min=low,
        endpoint_max=high,
        status_poll=_number(env, "INTERVIEW_AGENT_STATUS_POLL_SECONDS", 5.0, 1.0, 30.0),
        console_session_id=int(console) if console else None,
    )
