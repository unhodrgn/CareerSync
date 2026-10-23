"""The app refuses to start with an invalid AI_MODE or AI_MODE=llm without a key (no silent fallback). At
startup it logs the mode and model (never the key) and says which embedding model scores."""
import logging

import pytest
from fastapi.testclient import TestClient

from ai.embedding.model import HashingEmbedder
from ai.llm.client import LLMConfigError
from app import main
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


def test_startup_logs_mode_and_model_but_never_the_key(monkeypatch, caplog):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-secret-value")
    monkeypatch.setenv("LLM_MODEL", "claude-test-model")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"), TestClient(app):
        pass
    assert "AI_MODE=llm, LLM_MODEL=claude-test-model" in caplog.text
    assert "sk-test-secret-value" not in caplog.text


def _warm_up(monkeypatch, caplog, mode: str, configured: str) -> logging.LogRecord:
    monkeypatch.setattr(main, "get_embedder", HashingEmbedder)  # the fallback embedder, whatever is configured
    monkeypatch.setattr(main, "configured_model", lambda: configured)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        main.warm_up_embedder(mode)
    # Called directly here; the background warm-up of an earlier app start may log meanwhile from its own thread
    return next(
        r for r in caplog.records
        if r.name == "uvicorn.error" and "Embedding model" in r.getMessage() and r.threadName != "embedder-warm-up"
    )


def test_warm_up_reports_the_embedding_model_in_use(monkeypatch, caplog):
    record = _warm_up(monkeypatch, caplog, "llm", "hashing-ngram-v1")
    assert record.levelno == logging.INFO and record.getMessage() == "Embedding model ready: hashing-ngram-v1"


def test_warm_up_logs_an_error_when_llm_mode_scores_with_the_fallback(monkeypatch, caplog):
    record = _warm_up(monkeypatch, caplog, "llm", "intfloat/multilingual-e5-base")
    assert record.levelno == logging.ERROR
    assert "intfloat/multilingual-e5-base" in record.getMessage() and "hashing-ngram-v1" in record.getMessage()


def test_warm_up_only_warns_about_the_fallback_in_rules_mode(monkeypatch, caplog):
    record = _warm_up(monkeypatch, caplog, "rules", "intfloat/multilingual-e5-base")
    assert record.levelno == logging.WARNING
