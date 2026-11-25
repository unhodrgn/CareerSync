"""LLMClient: the only way the app calls an LLM, so the provider or model can be swapped without touching callers.

The mode is chosen only by `AI_MODE` (`rules`, the default in code, or `llm`); an API key alone never
enables the LLM. `get_llm_client()` returns None in `rules` mode. Every caller has a rule-based
fallback for that case, so the app and the tests run without network access.
"""
import json
import logging
import os
import re
import time
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

LLM_PROVIDERS = ("groq", "anthropic")
DEFAULT_PROVIDER = "groq"
DEFAULT_MODELS: dict[str, str] = {
    "groq": "openai/gpt-oss-120b",
    "anthropic": "claude-sonnet-5-5",
}
DEFAULT_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
DEFAULT_EFFORT = "low"

AI_MODES = ("rules", "llm")
DEFAULT_AI_MODE = "rules"

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
# Seconds per request; retries handle transient 429/5xx/network failures without blocking endlessly
LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_RETRIES = 2
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
# A response is usable only when the model finished on its own; refusal, truncation, pause_turn and a full
# context window are failures
_ANTHROPIC_FINISHED = ("end_turn", "stop_sequence")
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class LLMError(RuntimeError):
    """The model call failed or returned nothing usable (refusal, truncation, invalid JSON)."""


class LLMConfigError(RuntimeError):
    """AI_MODE is invalid, or AI_MODE=llm without LLM_API_KEY. Not an LLMError: callers must not fall back."""


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: type[T], max_tokens: int = 4000) -> T:
        """One request; the response is validated against `schema` (a Pydantic model)."""
        ...


class AnthropicClient:
    """Claude through the official SDK, with structured JSON output.

    Every failure leaves `complete_json` as an LLMError, so each caller falls back to its rules or template.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODELS["anthropic"],
        effort: str = DEFAULT_EFFORT,
        timeout: float = LLM_TIMEOUT_SECONDS,
    ):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=LLM_MAX_RETRIES)
        self.model = model
        self.effort = effort

    def complete_json(self, system: str, user: str, schema: type[T], max_tokens: int = 4000) -> T:
        sdk = self._anthropic
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort},
                output_format=schema,
            )
        except sdk.APIStatusError as e:  # 400, 401, 403, 404, 413, 429, 5xx, 529 overloaded, ...
            raise LLMError(f"LLM API error {type(e).__name__} {e.status_code}: {e.message}") from e
        except sdk.APIConnectionError as e:  # also APITimeoutError
            raise LLMError(f"LLM connection error {type(e).__name__}") from e
        except sdk.AnthropicError as e:  # e.g. APIResponseValidationError, CredentialsError
            raise LLMError(f"LLM client error {type(e).__name__}: {e}") from e
        except ValueError as e:  # the JSON did not validate against the schema (pydantic.ValidationError)
            raise LLMError(f"LLM output failed validation: {e}") from e
        except Exception as e:  # noqa: BLE001  (e.g. a TypeError when the SDK and the parameters disagree)
            log.exception("unexpected error from the LLM client")
            raise LLMError(f"LLM client failed unexpectedly: {type(e).__name__}: {e}") from e
        if response.stop_reason not in _ANTHROPIC_FINISHED or response.parsed_output is None:
            raise LLMError(f"LLM returned no usable output (stop_reason={response.stop_reason})")
        return response.parsed_output


class GroqClient:
    """OpenAI-compatible Groq chat completions via `httpx`, with Pydantic JSON validation.

    Every failure leaves `complete_json` as an LLMError, so each caller falls back to its rules or template.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODELS["groq"],
        effort: str = DEFAULT_EFFORT,
        timeout: float = LLM_TIMEOUT_SECONDS,
        max_retries: int = LLM_MAX_RETRIES,
    ):
        import httpx

        self._httpx = httpx
        self._client = httpx.Client(timeout=timeout)
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.max_retries = max_retries
        self._retry_backoff = 0.5
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, system: str, user: str, schema: type[T], max_tokens: int) -> dict[str, Any]:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_with_schema = (
            f"{system}\n\n"
            "Respond with a single valid JSON object matching this JSON Schema (no markdown fences, no commentary):\n"
            f"{schema_json}"
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": user},
            ],
        }
        if self.model.startswith("openai/gpt-oss") and self.effort in ("low", "medium", "high"):
            payload["reasoning_effort"] = self.effort
        return payload

    def complete_json(self, system: str, user: str, schema: type[T], max_tokens: int = 4000) -> T:
        payload = self._build_payload(system, user, schema, max_tokens)
        httpx = self._httpx
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(GROQ_CHAT_COMPLETIONS_URL, headers=self._headers, json=payload)
            except httpx.TimeoutException as e:
                if attempt < self.max_retries:
                    time.sleep(self._retry_backoff * (attempt + 1))
                    continue
                raise LLMError(f"LLM connection error {type(e).__name__}") from e
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    time.sleep(self._retry_backoff * (attempt + 1))
                    continue
                raise LLMError(f"LLM connection error {type(e).__name__}") from e
            except Exception as e:  # noqa: BLE001
                log.exception("unexpected error from the LLM client")
                raise LLMError(f"LLM client failed unexpectedly: {type(e).__name__}: {e}") from e

            if response.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                time.sleep(self._retry_backoff * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise LLMError(f"LLM API error HTTPStatusError {response.status_code}")
            break

        assert response is not None
        try:
            data = response.json()
        except ValueError as e:
            raise LLMError("LLM returned invalid JSON response envelope") from e

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMError("LLM returned no usable output (missing choices)")

        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if finish_reason != "stop" or not isinstance(content, str) or not content.strip():
            raise LLMError(f"LLM returned no usable output (finish_reason={finish_reason})")

        cleaned = _FENCE.sub("", content.strip()).strip()
        try:
            return schema.model_validate_json(cleaned)
        except (ValidationError, ValueError) as e:
            raise LLMError(f"LLM output failed validation: {e}") from e


def ai_mode() -> str:
    """`AI_MODE`, case-insensitive; unset or empty means `rules`."""
    mode = (os.getenv("AI_MODE") or "").strip().lower() or DEFAULT_AI_MODE
    if mode not in AI_MODES:
        raise LLMConfigError(f"Invalid AI_MODE={os.getenv('AI_MODE')!r}; expected one of: {', '.join(AI_MODES)}")
    return mode


def llm_provider() -> str:
    """`LLM_PROVIDER`, case-insensitive; unset or empty means `DEFAULT_PROVIDER` (`groq`)."""
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower() or DEFAULT_PROVIDER
    if provider not in LLM_PROVIDERS:
        raise LLMConfigError(
            f"Invalid LLM_PROVIDER={os.getenv('LLM_PROVIDER')!r}; expected one of: {', '.join(LLM_PROVIDERS)}"
        )
    return provider


def _api_key(provider: str) -> str:
    # LLM_API_KEY takes precedence; when provider is groq, fall back to GROQ_API_KEY (D91).
    # ANTHROPIC_API_KEY is deliberately never read (doc issue 1).
    key = (os.getenv("LLM_API_KEY") or "").strip()
    if key or provider != "groq":
        return key
    return (os.getenv("GROQ_API_KEY") or "").strip()


def llm_model() -> str:
    """The model `llm` mode calls (`LLM_MODEL`; unset, empty or whitespace means the active provider's default)."""
    explicit = os.getenv("LLM_MODEL")
    if explicit and explicit.strip():
        return explicit.strip()
    return DEFAULT_MODELS[llm_provider()]


def _checked_config() -> tuple[str, str, str]:
    mode = ai_mode()
    provider = llm_provider()
    key = _api_key(provider)
    if mode == "llm" and not key:
        if provider == "groq":
            raise LLMConfigError("AI_MODE=llm with LLM_PROVIDER=groq requires LLM_API_KEY or GROQ_API_KEY")
        raise LLMConfigError("AI_MODE=llm with LLM_PROVIDER=anthropic requires LLM_API_KEY")
    return mode, provider, key


def check_llm_config() -> str:
    """Validate the AI settings at startup; returns the mode. Raises LLMConfigError."""
    mode, _provider, key = _checked_config()
    if mode == "rules" and key:
        log.info("AI_MODE=rules: API key is set but ignored")
    return mode


def get_llm_client() -> LLMClient | None:
    """The configured client in `llm` mode, None in `rules` mode (even when a key is set)."""
    mode, provider, key = _checked_config()
    if mode == "rules":
        return None
    effort = (os.getenv("LLM_EFFORT") or "").strip() or DEFAULT_EFFORT
    if provider == "groq":
        return GroqClient(api_key=key, model=llm_model(), effort=effort)
    return AnthropicClient(api_key=key, model=llm_model(), effort=effort)
