"""AI_MODE selects rules or LLM explicitly; an API key alone never enables the LLM. No request is sent."""
import pytest

from ai.llm.client import AnthropicClient, LLMConfigError, ai_mode, check_llm_config, get_llm_client


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("AI_MODE", "LLM_API_KEY", "ANTHROPIC_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)


def test_key_alone_does_not_enable_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    assert ai_mode() == "rules"
    assert get_llm_client() is None


def test_rules_mode_ignores_key(monkeypatch):
    monkeypatch.setenv("AI_MODE", "rules")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    assert check_llm_config() == "rules"
    assert get_llm_client() is None


@pytest.mark.parametrize("value, expected", [("", "rules"), ("  ", "rules"), (" RULES ", "rules"), ("LLM", "llm")])
def test_mode_is_case_insensitive_and_empty_means_rules(monkeypatch, value, expected):
    monkeypatch.setenv("AI_MODE", value)
    assert ai_mode() == expected


@pytest.mark.parametrize("value", ["true", "lmm", "rule-based"])
def test_invalid_mode_is_an_error(monkeypatch, value):
    monkeypatch.setenv("AI_MODE", value)
    with pytest.raises(LLMConfigError, match="AI_MODE"):
        check_llm_config()
    with pytest.raises(LLMConfigError):
        get_llm_client()


@pytest.mark.parametrize("key", [None, "", "  "])
def test_llm_mode_without_key_is_an_error(monkeypatch, key):
    monkeypatch.setenv("AI_MODE", "llm")
    if key is not None:
        monkeypatch.setenv("LLM_API_KEY", key)
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        check_llm_config()
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        get_llm_client()


def test_anthropic_api_key_is_not_read(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        get_llm_client()


def test_llm_mode_with_key_builds_the_client(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "claude-test-model")
    assert check_llm_config() == "llm"
    client = get_llm_client()  # constructing the SDK client sends no request
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-test-model"
