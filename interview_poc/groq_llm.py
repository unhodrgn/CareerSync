"""Groq for the PoC through LiveKit's official Groq plugin (a temporary, standalone integration).

CareerSync itself calls its LLM only through ai/llm/client.py (AI rule 2). This PoC does not touch that file: it uses the
LiveKit Groq plugin directly, as decided for the isolated prototype, with the key passed explicitly (`api_key=`).
No Anthropic API is called anywhere in this folder.

Compatibility notes for openai/gpt-oss-120b, checked against the installed livekit-plugins-groq 1.8.12 source, the LiveKit
Groq LLM plugin guide and Groq's model pages (not by a live call; `verify_llm.py` does that):
- The plugin wraps the OpenAI plugin and points it at Groq's OpenAI-compatible endpoint. `LLMModels` is only a type hint:
  any string is accepted, and `openai/gpt-oss-120b` is in the plugin's own list.
- The plugin sends no `temperature`/`top_p` unless set, and this module never sets them.
- gpt-oss is a reasoning model. `reasoning_effort` is sent explicitly (`low` by default, as the plugin would also do for
  gpt-oss). A model without reasoning (e.g. llama-3.3-70b-versatile) gets no `reasoning_effort` at all.
- Reasoning text arrives in a separate field of the stream, not in `content`: the plugin drops chunks without content, so only
  the answer is spoken. Groq's docs do not say whether reasoning tokens count against `max_completion_tokens`, so the budget
  is generous (1024) and the prompts, not the limit, keep the answer short. An answer that is empty anyway raises `empty_output`.
- Requests never end with an assistant message: the prompt is one system message and one user message.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from livekit.agents import APIConnectionError, APIConnectOptions, APIStatusError, APITimeoutError, llm
from livekit.plugins import groq

from config import LLM_TIMEOUT_SECONDS

log = logging.getLogger("interview_poc.groq_llm")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"  # the plugin's default, passed explicitly so the host is visible in one place
# Room for the model's own reasoning plus one or two spoken sentences; the prompts ask for brevity, the output is screened.
MAX_OUTPUT_TOKENS = 1024


class LlmUnavailable(RuntimeError):
    """The model call failed. `code` is safe to log and show (never contains a key or the prompt)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class LlmResult:
    text: str
    ttft_s: float | None
    total_s: float
    model: str


class VoiceGroq(groq.LLM):
    """The plugin's LLM with the PoC defaults: Groq's endpoint, a token budget, and an explicit reasoning effort."""

    def __init__(self, *, model: str, api_key: str, reasoning_effort: str = "", **kwargs) -> None:
        kwargs.setdefault("base_url", GROQ_BASE_URL)
        kwargs.setdefault("max_completion_tokens", MAX_OUTPUT_TOKENS)
        if reasoning_effort:  # empty = not sent (a model without reasoning rejects the field)
            kwargs["reasoning_effort"] = reasoning_effort
        super().__init__(model=model, api_key=api_key, **kwargs)


async def complete_text(model: llm.LLM, *, system: str, user: str, timeout: float = LLM_TIMEOUT_SECONDS) -> LlmResult:
    """One non-streaming-looking call: collect the streamed answer into a string and time it.

    The caller screens the text before anything is spoken, so streaming to the TTS is not used. Any failure raises
    `LlmUnavailable`; there is no retry on another model.
    """
    ctx = llm.ChatContext()
    ctx.add_message(role="system", content=system)
    ctx.add_message(role="user", content=user)
    started = time.perf_counter()
    first: float | None = None
    parts: list[str] = []

    async def run() -> None:
        nonlocal first
        async with model.chat(chat_ctx=ctx, conn_options=APIConnectOptions(max_retry=1, retry_interval=1.0, timeout=timeout)) as stream:
            async for chunk in stream:
                delta = chunk.delta
                if delta is not None and delta.content:
                    if first is None:
                        first = time.perf_counter() - started
                    parts.append(delta.content)

    try:
        await asyncio.wait_for(run(), timeout=timeout + 5.0)
    except asyncio.TimeoutError as e:
        raise LlmUnavailable("timeout") from e
    except APIStatusError as e:
        raise LlmUnavailable(f"http_{e.status_code}", _safe_detail(e)) from e
    except APITimeoutError as e:
        raise LlmUnavailable("timeout") from e
    except APIConnectionError as e:
        raise LlmUnavailable("connection") from e
    except Exception as e:  # noqa: BLE001  (any other provider failure also ends the PoC session politely)
        log.exception("unexpected LLM failure")
        raise LlmUnavailable(type(e).__name__) from e
    text = "".join(parts).strip()
    if not text:
        raise LlmUnavailable("empty_output")
    return LlmResult(text=text, ttft_s=first, total_s=time.perf_counter() - started, model=model.model)


def _safe_detail(e: APIStatusError) -> str:
    """The API's error message (e.g. which parameter a 400 rejected), shortened. It never contains the key."""
    body = getattr(e, "body", None)
    message = ""
    if isinstance(body, dict):
        err = body.get("error")
        message = str(err.get("message") if isinstance(err, dict) else body.get("message") or "")
    return (message or str(e))[:300]
