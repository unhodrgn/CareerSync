"""The request the PoC sends to Groq, checked against the pinned LiveKit Groq plugin with a fake client (no network).

This is the offline half of "verify that openai/gpt-oss-120b is supported": the plugin lists the model, sends no sampling
parameters, sets `reasoning_effort` explicitly (only for a reasoning model), keeps reasoning text out of the answer and never
ends a request with an assistant message. `verify_llm.py` is the live half (it needs a key and is run by the developer).
"""
import asyncio
import typing
from types import SimpleNamespace

import httpx2
import openai
import pytest
from livekit.plugins.groq.models import LLMModels
from openai.types.chat import ChatCompletionChunk

from groq_llm import GROQ_BASE_URL, MAX_OUTPUT_TOKENS, LlmUnavailable, VoiceGroq, complete_text

MODEL = "openai/gpt-oss-120b"


def chunk(content=None, *, reasoning=None, finish=None):
    delta = {"role": "assistant"}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning"] = reasoning  # Groq streams gpt-oss reasoning in its own field, never in `content`
    return ChatCompletionChunk.model_validate(
        {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 0, "model": MODEL,
         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    )


def usage_chunk():
    return ChatCompletionChunk.model_validate(
        {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 0, "model": MODEL, "choices": [],
         "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17, "completion_tokens_details": {"reasoning_tokens": 3}}}
    )


def completion_stream(text_parts, reasoning_parts=()):
    events = [chunk(reasoning=r) for r in reasoning_parts] + [chunk(t) for t in text_parts] + [chunk(finish="stop"), usage_chunk()]

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            async def gen():
                for e in events:
                    yield e

            return gen()

    return Stream()


class FakeClient:
    """Stands in for openai.AsyncClient: records every chat.completions.create call."""

    def __init__(self, text_parts=("방금 말씀하신 ", "내용은 어떻게 검증하나요?"), reasoning_parts=(), error=None):
        self.calls = []
        self._parts, self._reasoning, self._error = text_parts, reasoning_parts, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(list=self._list)
        self._base_url = SimpleNamespace(netloc=b"api.groq.com", host="api.groq.com")

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return completion_stream(self._parts, self._reasoning)

    async def _list(self):  # a token-free prewarm request; not a completion, so it is not recorded in `calls`
        return SimpleNamespace(data=[])


def make(client, model=MODEL, reasoning_effort="low"):
    return VoiceGroq(model=model, api_key="test-key", reasoning_effort=reasoning_effort, client=client)


def test_the_model_is_in_the_pinned_plugins_model_list():
    assert MODEL in typing.get_args(LLMModels)  # the plugin's own production list (the type is only a hint: any string is accepted)


def test_request_shape_for_gpt_oss_120b():
    client = FakeClient()
    result = asyncio.run(complete_text(make(client), system="SYSTEM TEXT", user="USER TEXT"))
    assert result.text == "방금 말씀하신 내용은 어떻게 검증하나요?" and result.ttft_s is not None and result.model == MODEL
    (call,) = client.calls
    assert call["model"] == MODEL
    assert call["reasoning_effort"] == "low"  # sent explicitly
    assert call["stream"] is True and call["max_completion_tokens"] == MAX_OUTPUT_TOKENS == 1024 and "max_tokens" not in call
    # No sampling parameters at all
    assert "temperature" not in call and "top_p" not in call and "top_k" not in call
    # The system prompt and the user turn are two messages; the last one is the user's, never an assistant message (no prefill)
    assert [m["role"] for m in call["messages"]] == ["system", "user"]
    assert "SYSTEM TEXT" in str(call["messages"][0]["content"]) and "USER TEXT" in str(call["messages"][1]["content"])
    assert "tool_choice" not in call and call["tools"] is openai.omit  # no tools, no forced tool choice


def test_a_model_without_reasoning_gets_no_reasoning_effort():
    client = FakeClient()
    asyncio.run(complete_text(make(client, model="llama-3.3-70b-versatile", reasoning_effort=""), system="S", user="U"))
    assert "reasoning_effort" not in client.calls[0]  # a model without reasoning would reject the field
    assert client.calls[0]["model"] == "llama-3.3-70b-versatile"


def test_an_explicit_reasoning_effort_is_sent():
    client = FakeClient()
    asyncio.run(complete_text(make(client, reasoning_effort="medium"), system="S", user="U"))
    assert client.calls[0]["reasoning_effort"] == "medium"


def test_reasoning_text_is_never_part_of_the_answer():
    client = FakeClient(reasoning_parts=("Let me think about idempotency. ", "The user asked ..."))
    result = asyncio.run(complete_text(make(client), system="S", user="U"))
    assert result.text == "방금 말씀하신 내용은 어떻게 검증하나요?"
    assert "think" not in result.text and "user asked" not in result.text


@pytest.mark.parametrize("kwargs", [{"text_parts": ("   ",)}, {"text_parts": (), "reasoning_parts": ("all the budget went into thinking",)}])
def test_empty_output_is_an_error(kwargs):
    with pytest.raises(LlmUnavailable) as e:
        asyncio.run(complete_text(make(FakeClient(**kwargs)), system="S", user="U"))
    assert e.value.code == "empty_output"


def test_the_key_is_passed_explicitly_and_only_groq_is_called(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    llm = VoiceGroq(model=MODEL, api_key="explicit-key")  # would raise ValueError if it needed GROQ_API_KEY
    assert llm.model == MODEL and llm.provider == "api.groq.com"
    assert str(llm._client.base_url).startswith(GROQ_BASE_URL) and llm._client.api_key == "explicit-key"


def test_the_plugin_refuses_to_start_without_a_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        VoiceGroq(model=MODEL, api_key="")


def _status_error(code, message):
    response = httpx2.Response(code, request=httpx2.Request("POST", f"{GROQ_BASE_URL}/chat/completions"))
    return openai.APIStatusError(message, response=response, body={"error": {"type": "invalid_request_error", "message": message}})


def test_a_rejected_request_is_reported_with_the_reason_and_not_retried():
    client = FakeClient(error=_status_error(400, "reasoning_effort is not supported for this model"))
    with pytest.raises(LlmUnavailable) as e:
        asyncio.run(complete_text(make(client, model="some-other-model"), system="S", user="U"))
    assert e.value.code == "http_400" and "reasoning_effort" in e.value.detail
    assert len(client.calls) == 1  # no retry (a 400 is not retryable), and above all no other model
