"""Test setup of the PoC: its modules are top-level, and no test may read a real .env or call a network service."""
import sys
from pathlib import Path

import pytest

POC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC_DIR))

SECRET_VARIABLES = (
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ANAM_API_KEY", "ANAM_AVATAR_ID",
    "GROQ_API_KEY", "LLM_MODEL", "AI_MODE", "POC_LLM_REASONING_EFFORT",
    "LLM_API_KEY", "ANTHROPIC_API_KEY",  # no longer read by the PoC: scrubbed so a stale shell value cannot matter
    "POC_AVATAR", "POC_TTS_VOICE", "POC_MASK_NAMES",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """Tests pass their settings explicitly; a developer's shell variables must not leak in."""
    for name in SECRET_VARIABLES:
        monkeypatch.delenv(name, raising=False)
