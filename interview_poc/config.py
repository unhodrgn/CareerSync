"""Settings of the standalone interview PoC.

Everything comes from environment variables. This folder's own `interview_poc/.env` (created by the developer, git-ignored)
is loaded first, explicitly by path: the CareerSync repo-root `.env` is never read here. Only variable *names* appear in
the repository; values never do, and `Settings` hides its secrets from `repr`.

Nothing here imports `app.*` or `ai.*` (the PoC is isolated from CareerSync).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

POC_DIR = Path(__file__).resolve().parent
ENV_FILE = POC_DIR / ".env"
WEB_DIR = POC_DIR / "web"
RUNS_DIR = POC_DIR / ".runs"

AGENT_NAME = "careersync-interview-poc"
# The PoC calls Groq through LiveKit's Groq plugin (a standalone choice; CareerSync's ai/llm/client.py is not used or imported).
# Never switched silently: a failing model ends the session. For a comparison run, set LLM_MODEL explicitly.
DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"
# Sample voice from LiveKit's Cartesia page. It documents no Korean voice, so set POC_TTS_VOICE after listening to Korean output.
DEFAULT_TTS_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
STT_MODEL = "deepgram/nova-3"  # LiveKit Inference; `ko` is listed for this model
TTS_MODEL = "cartesia/sonic-3"  # LiveKit Inference; `ko` is listed for this model
LANGUAGE = "ko"

REASONING_EFFORTS = ("low", "medium", "high")  # the values Groq documents for openai/gpt-oss-120b and gpt-oss-20b
DEFAULT_REASONING_EFFORT = "low"
REASONING_MODEL_PREFIX = "openai/gpt-oss"  # only these models get a reasoning effort by default; others never receive the field

# Anam's Free plan ends a session after 3 minutes; the PoC stops itself a little earlier.
WRAP_UP_AT_SECONDS = 140.0  # no new question after this; close politely
HARD_STOP_SECONDS = 168.0  # leave the room whatever is happening
ANSWER_IDLE_SECONDS = 30.0  # nobody answers: end the practice politely
AVATAR_JOIN_TIMEOUT_SECONDS = 30.0
LLM_TIMEOUT_SECONDS = 20.0


class ConfigError(RuntimeError):
    """A required setting is missing or invalid. Messages name variables, never values."""


@dataclass(frozen=True)
class Settings:
    livekit_url: str = ""
    livekit_api_key: str = field(default="", repr=False)
    livekit_api_secret: str = field(default="", repr=False)
    anam_api_key: str = field(default="", repr=False)
    anam_avatar_id: str = ""
    groq_api_key: str = field(default="", repr=False)
    llm_model: str = DEFAULT_LLM_MODEL
    reasoning_effort: str = ""  # "" = not sent (a model without reasoning rejects the field)
    tts_voice: str = DEFAULT_TTS_VOICE
    avatar_enabled: bool = True
    mask_names: tuple[str, ...] = ()


def load_env_file() -> None:
    """Load interview_poc/.env if it exists. Shell variables win. Never searches parent folders."""
    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=False)


def _get(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def load_settings(env: Mapping[str, str] | None = None, *, role: str = "agent") -> Settings:
    """Validate and collect the settings. `role` is `agent` (needs every key), `token` (LiveKit keys only) or `llm` (LLM only)."""
    env = os.environ if env is None else env
    if role not in ("agent", "token", "llm"):
        raise ValueError(f"unknown role {role!r}")

    avatar = (_get(env, "POC_AVATAR") or "on").lower()
    if avatar not in ("on", "off"):
        raise ConfigError("POC_AVATAR must be 'on' or 'off'")
    model = _get(env, "LLM_MODEL") or DEFAULT_LLM_MODEL
    if role in ("agent", "llm") and model.lower().startswith("claude"):
        # An old .env may still name the Anthropic model; the PoC calls Groq only, so say so instead of sending it to Groq.
        raise ConfigError("LLM_MODEL names an Anthropic model; this PoC calls Groq only (default openai/gpt-oss-120b): fix or remove LLM_MODEL")
    effort = _get(env, "POC_LLM_REASONING_EFFORT").lower()
    if effort and effort not in REASONING_EFFORTS:
        raise ConfigError(f"POC_LLM_REASONING_EFFORT must be one of: {', '.join(REASONING_EFFORTS)}")
    if not effort and model.startswith(REASONING_MODEL_PREFIX):
        effort = DEFAULT_REASONING_EFFORT

    required = [] if role == "llm" else ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
    if role in ("agent", "llm"):
        required += ["GROQ_API_KEY"]
    if role == "agent" and avatar == "on":
        required += ["ANAM_API_KEY", "ANAM_AVATAR_ID"]
    missing = [name for name in required if not _get(env, name)]
    if missing:
        raise ConfigError(f"Missing environment variables (see interview_poc/.env.example): {', '.join(missing)}")

    if role in ("agent", "llm") and _get(env, "AI_MODE").lower() != "llm":
        # D5/D12: a key alone never turns the LLM on; AI_MODE=llm must be explicit.
        raise ConfigError("AI_MODE=llm is required: the LLM is only called when AI_MODE=llm is set explicitly")

    names = tuple(n.strip() for n in _get(env, "POC_MASK_NAMES").split(",") if n.strip())
    return Settings(
        livekit_url=_get(env, "LIVEKIT_URL"),
        livekit_api_key=_get(env, "LIVEKIT_API_KEY"),
        livekit_api_secret=_get(env, "LIVEKIT_API_SECRET"),
        anam_api_key=_get(env, "ANAM_API_KEY"),
        anam_avatar_id=_get(env, "ANAM_AVATAR_ID"),
        groq_api_key=_get(env, "GROQ_API_KEY"),
        llm_model=model,
        reasoning_effort=effort,
        tts_voice=_get(env, "POC_TTS_VOICE") or DEFAULT_TTS_VOICE,
        avatar_enabled=avatar == "on",
        mask_names=names,
    )
