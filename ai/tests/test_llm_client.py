"""AI_MODE selects rules or LLM explicitly; an API key alone never enables the LLM. Every failure of a call
becomes an LLMError, so callers fall back to rules. No request is sent: the SDK's `messages` is replaced."""
import logging
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from ai.llm.client import (
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    AnthropicClient,
    LLMConfigError,
    LLMError,
    ai_mode,
    check_llm_config,
    get_llm_client,
)


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


def test_sdk_client_timeout_and_retries():
    sdk = AnthropicClient(api_key="sk-test")._client
    assert (sdk.timeout, sdk.max_retries) == (LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES) == (30.0, 2)


# ── complete_json failures (the SDK's messages.parse is replaced; nothing is sent) ──

# The SDK module as the client loaded it: `anthropic` is imported only in ai/llm/client.py (CLAUDE.md AI rule 2).
# Building the client sends no request.
sdk = AnthropicClient(api_key="sk-test")._anthropic


class _Out(BaseModel):
    answer: str


def _client(outcome) -> AnthropicClient:
    """A client whose messages.parse raises `outcome` if it is an exception, else returns it."""

    def parse(**_kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    client = AnthropicClient(api_key="sk-test")
    client._client = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    return client


def _sdk_error(cls: type[Exception], **attrs) -> Exception:
    """An SDK exception without HTTP objects: complete_json reads only its type, `status_code` and `message`."""
    error = cls.__new__(cls)
    Exception.__init__(error, attrs.get("message", ""))
    for name, value in attrs.items():
        setattr(error, name, value)
    return error


def _validation_error() -> ValidationError:
    try:
        _Out.model_validate_json('{"answer": ')  # what a truncated JSON reply raises inside messages.parse
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


def _response(stop_reason: str, parsed: _Out | None):
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_sdk_error(sdk.AuthenticationError, status_code=401, message="invalid x-api-key"), "AuthenticationError 401"),
        (_sdk_error(sdk.PermissionDeniedError, status_code=403, message="forbidden"), "PermissionDeniedError 403"),
        (_sdk_error(sdk.NotFoundError, status_code=404, message="model not found"), "NotFoundError 404"),
        (_sdk_error(sdk.BadRequestError, status_code=400, message="bad request"), "BadRequestError 400"),
        (_sdk_error(sdk.RateLimitError, status_code=429, message="rate limited"), "RateLimitError 429"),
        (_sdk_error(sdk.InternalServerError, status_code=500, message="server error"), "InternalServerError 500"),
        (_sdk_error(sdk.OverloadedError, status_code=529, message="overloaded"), "OverloadedError 529"),
        (_sdk_error(sdk.APITimeoutError), "APITimeoutError"),
        (_sdk_error(sdk.APIConnectionError), "APIConnectionError"),
        (_sdk_error(sdk.APIResponseValidationError), "APIResponseValidationError"),
        (_sdk_error(sdk.CredentialsError), "CredentialsError"),
        (_validation_error(), "failed validation"),
        (TypeError("unexpected keyword argument 'output_config'"), "TypeError"),
    ],
)
def test_every_failure_of_a_call_is_an_llm_error(error, expected):
    with pytest.raises(LLMError, match=expected):
        _client(error).complete_json("system", "user", _Out)


def test_an_unexpected_error_is_logged_with_its_stack(caplog):
    with caplog.at_level(logging.ERROR, logger="ai.llm.client"), pytest.raises(LLMError):
        _client(TypeError("boom")).complete_json("system", "user", _Out)
    record = next(r for r in caplog.records if r.name == "ai.llm.client")
    assert record.levelno == logging.ERROR and record.exc_info is not None


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens", "pause_turn", "model_context_window_exceeded", "tool_use"])
def test_a_response_the_model_did_not_finish_is_an_llm_error(stop_reason):
    with pytest.raises(LLMError, match=stop_reason):
        _client(_response(stop_reason, _Out(answer="partial"))).complete_json("system", "user", _Out)


def test_a_finished_response_without_parsed_output_is_an_llm_error():
    with pytest.raises(LLMError, match="end_turn"):
        _client(_response("end_turn", None)).complete_json("system", "user", _Out)


@pytest.mark.parametrize("stop_reason", ["end_turn", "stop_sequence"])
def test_a_finished_response_returns_the_parsed_output(stop_reason):
    out = _client(_response(stop_reason, _Out(answer="ok"))).complete_json("system", "user", _Out)
    assert out == _Out(answer="ok")
