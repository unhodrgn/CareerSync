"""LLMClient: the only way the app calls an LLM, so the model can be swapped without touching callers.

The mode is chosen only by `AI_MODE` (`rules`, the default, or `llm`); an API key alone never
enables the LLM. `get_llm_client()` returns None in `rules` mode. Every caller has a rule-based
fallback for that case, so the app and the tests run without network access.
"""
import logging
import os
from typing import Protocol, TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-sonnet-5-5"

AI_MODES = ("rules", "llm")
DEFAULT_AI_MODE = "rules"

# Seconds per request; the SDK retries twice, so a failing call ends after about three times this
LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_RETRIES = 2
# A response is usable only when the model finished on its own; refusal, truncation, pause_turn and a full
# context window are failures
_FINISHED = ("end_turn", "stop_sequence")


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

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, effort: str = "low", timeout: float = LLM_TIMEOUT_SECONDS):
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
        if response.stop_reason not in _FINISHED or response.parsed_output is None:
            raise LLMError(f"LLM returned no usable output (stop_reason={response.stop_reason})")
        return response.parsed_output


def ai_mode() -> str:
    """`AI_MODE`, case-insensitive; unset or empty means `rules`."""
    mode = (os.getenv("AI_MODE") or "").strip().lower() or DEFAULT_AI_MODE
    if mode not in AI_MODES:
        raise LLMConfigError(f"Invalid AI_MODE={os.getenv('AI_MODE')!r}; expected one of: {', '.join(AI_MODES)}")
    return mode


def _api_key() -> str:
    # Only LLM_API_KEY; ANTHROPIC_API_KEY is deliberately not read (doc issue 1)
    return (os.getenv("LLM_API_KEY") or "").strip()


def llm_model() -> str:
    """The model `llm` mode calls (LLM_MODEL; unset, empty or whitespace only means the default)."""
    return (os.getenv("LLM_MODEL") or "").strip() or DEFAULT_MODEL


def _checked_mode() -> str:
    mode = ai_mode()
    if mode == "llm" and not _api_key():
        raise LLMConfigError("AI_MODE=llm requires LLM_API_KEY")
    return mode


def check_llm_config() -> str:
    """Validate the AI settings at startup; returns the mode. Raises LLMConfigError."""
    mode = _checked_mode()
    if mode == "rules" and _api_key():
        log.info("AI_MODE=rules: LLM_API_KEY is set but ignored")
    return mode


def get_llm_client() -> LLMClient | None:
    """The configured client in `llm` mode, None in `rules` mode (even when a key is set)."""
    if _checked_mode() == "rules":
        return None
    return AnthropicClient(
        api_key=_api_key(),
        model=llm_model(),
        effort=(os.getenv("LLM_EFFORT") or "").strip() or "low",
    )
