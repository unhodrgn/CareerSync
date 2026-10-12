"""The app refuses to start with an invalid AI_MODE or AI_MODE=llm without a key (no silent fallback)."""
import pytest
from fastapi.testclient import TestClient

from ai.llm.client import LLMConfigError
from app.main import app
from app.services import ai_runtime


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("AI_MODE", "LLM_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_startup_fails_in_llm_mode_without_key(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")  # not read
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        with TestClient(app):
            pass


def test_startup_fails_on_invalid_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "true")
    with pytest.raises(LLMConfigError, match="AI_MODE"):
        with TestClient(app):
            pass


def test_default_mode_starts_and_ignores_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert ai_runtime.llm() is None
