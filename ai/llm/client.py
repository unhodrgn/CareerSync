"""LLMClient: the only way the app calls an LLM, so the model can be swapped without touching callers.

`get_llm_client()` returns None when no API key is configured. Every caller has a rule-based
fallback for that case, so the app and the tests run without network access.
"""
import logging
import os
from typing import Protocol, TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"


class LLMError(RuntimeError):
    """The model call failed or returned nothing usable (refusal, truncation, invalid JSON)."""


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: type[T], max_tokens: int = 4000) -> T:
        """One request; the response is validated against `schema` (a Pydantic model)."""
        ...


class AnthropicClient:
    """Claude through the official SDK, with structured JSON output."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, effort: str = "low", timeout: float = 60.0):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.effort = effort

    def complete_json(self, system: str, user: str, schema: type[T], max_tokens: int = 4000) -> T:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort},
                output_format=schema,
            )
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"LLM API error {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError("LLM connection error") from e
        except ValueError as e:  # the JSON did not validate against the schema (pydantic.ValidationError)
            raise LLMError(f"LLM output failed validation: {e}") from e
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            raise LLMError(f"LLM returned no usable output (stop_reason={response.stop_reason})")
        return response.parsed_output


def get_llm_client() -> LLMClient | None:
    """The configured client, or None when LLM_API_KEY / ANTHROPIC_API_KEY is not set."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return AnthropicClient(
        api_key=api_key,
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
        effort=os.getenv("LLM_EFFORT", "low"),
    )
