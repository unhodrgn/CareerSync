"""AI_MODE and LLM_PROVIDER select rules or LLM explicitly; keys alone never enable the LLM.
Every failure of a call becomes an LLMError, so callers fall back to rules. No real network request is sent."""
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from ai.llm.client import (
    DEFAULT_MODEL,
    DEFAULT_MODELS,
    DEFAULT_PROVIDER,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    AnthropicClient,
    GroqClient,
    LLMConfigError,
    LLMError,
    ai_mode,
    check_llm_config,
    get_llm_client,
    llm_model,
    llm_provider,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("AI_MODE", "LLM_PROVIDER", "LLM_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "LLM_MODEL", "LLM_EFFORT"):
        monkeypatch.delenv(key, raising=False)


def test_key_alone_does_not_enable_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
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


@pytest.mark.parametrize("value", ["unknown", "openai", "grok"])
def test_invalid_provider_is_an_error(monkeypatch, value):
    monkeypatch.setenv("LLM_PROVIDER", value)
    with pytest.raises(LLMConfigError, match="LLM_PROVIDER"):
        check_llm_config()
    with pytest.raises(LLMConfigError, match="LLM_PROVIDER"):
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
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        get_llm_client()


def test_anthropic_provider_does_not_fall_back_to_groq_api_key(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-only")
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        get_llm_client()


def test_default_provider_is_groq_with_groq_key_fallback(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-fallback")
    assert llm_provider() == DEFAULT_PROVIDER == "groq"
    assert check_llm_config() == "llm"
    client = get_llm_client()
    assert isinstance(client, GroqClient)
    assert llm_model() == client.model == DEFAULT_MODELS["groq"] == DEFAULT_MODEL == "openai/gpt-oss-120b"
    assert client.effort == "low"
    assert client._headers["Authorization"] == "Bearer gsk-fallback"


def test_llm_api_key_takes_precedence_over_groq_api_key(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "gsk-primary")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-fallback")
    client = get_llm_client()
    assert isinstance(client, GroqClient)
    assert client._headers["Authorization"] == "Bearer gsk-primary"


def test_anthropic_provider_with_key_builds_anthropic_client(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "claude-test-model")
    assert check_llm_config() == "llm"
    client = get_llm_client()  # constructing the SDK client sends no request
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-test-model"


@pytest.mark.parametrize("blank", [None, "", "  \t "], ids=["missing", "empty", "whitespace"])
def test_unset_or_blank_llm_model_and_effort_mean_the_defaults(monkeypatch, blank):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    if blank is not None:
        monkeypatch.setenv("LLM_MODEL", blank)
        monkeypatch.setenv("LLM_EFFORT", blank)
    client = get_llm_client()
    assert llm_model() == client.model == DEFAULT_MODELS["anthropic"]
    assert client.effort == "low"


def test_set_llm_model_and_effort_are_used(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "claude-test-model")
    monkeypatch.setenv("LLM_EFFORT", "high")
    client = get_llm_client()
    assert llm_model() == client.model == "claude-test-model"
    assert client.effort == "high"


def test_sdk_client_timeout_and_retries():
    anthropic_sdk = AnthropicClient(api_key="sk-test")._client
    groq_client = GroqClient(api_key="gsk-test")
    assert (anthropic_sdk.timeout, anthropic_sdk.max_retries) == (LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES) == (30.0, 2)
    assert (groq_client.timeout, groq_client.max_retries) == (LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES) == (30.0, 2)


# ── complete_json failures (Anthropic SDK mocked; nothing is sent) ──

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


# ── GroqClient via httpx.MockTransport (no real HTTP calls) ──


def _groq_client(handler, *, model: str = "openai/gpt-oss-120b", effort: str = "low", max_retries: int = 2) -> GroqClient:
    client = GroqClient(api_key="gsk-test-secret", model=model, effort=effort, max_retries=max_retries)
    client._retry_backoff = 0
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_groq_client_sends_schema_and_parses_fenced_json():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer gsk-test-secret"
        payload = json.loads(request.content.decode("utf-8"))
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '```json\n{"answer": "ok"}\n```'}}
                ]
            },
        )

    out = _groq_client(handler).complete_json("system rules", "user data", _Out, max_tokens=2048)
    assert out == _Out(answer="ok")
    payload = captured[0]
    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["max_completion_tokens"] == 2048
    assert payload["reasoning_effort"] == "low"
    assert payload["response_format"] == {"type": "json_object"}
    assert "answer" in payload["messages"][0]["content"]
    assert payload["messages"][1] == {"role": "user", "content": "user data"}


def test_groq_client_omits_reasoning_effort_for_non_gpt_oss_models():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"answer": "ok"}'}}]})

    _groq_client(handler, model="llama-3.3-70b-versatile").complete_json("sys", "usr", _Out)
    assert "reasoning_effort" not in captured[0]


def test_groq_client_retries_transient_errors_and_succeeds():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "rate_limit"})
        if attempts == 2:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"answer": "ok"}'}}]})

    out = _groq_client(handler, max_retries=2).complete_json("sys", "usr", _Out)
    assert attempts == 3 and out == _Out(answer="ok")


def test_groq_client_does_not_retry_client_errors_and_never_exposes_key():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LLMError, match="HTTPStatusError 401") as exc:
        _groq_client(handler, max_retries=2).complete_json("sys", "usr", _Out)
    assert attempts == 1
    assert "gsk-test-secret" not in str(exc.value)


@pytest.mark.parametrize("finish_reason", ["length", "content_filter", None])
def test_groq_client_rejects_unfinished_or_invalid_responses(finish_reason):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": finish_reason, "message": {"content": '{"answer": "partial"}'}}]},
        )

    with pytest.raises(LLMError):
        _groq_client(handler).complete_json("sys", "usr", _Out)


def test_groq_client_invalid_json_and_connection_exhaustion():
    def bad_json(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{not-json"}}]})

    with pytest.raises(LLMError, match="failed validation"):
        _groq_client(bad_json).complete_json("sys", "usr", _Out)

    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with pytest.raises(LLMError, match="ConnectError"):
        _groq_client(broken, max_retries=1).complete_json("sys", "usr", _Out)
