"""The Groq adapter with a fake plugin LLM: what it sends, the timeout, an empty answer. No network."""
import asyncio
import time
from types import SimpleNamespace

import pytest

from ai.interview import ask, compose, safe_text
from ai.interview.llm import TurnLlmOut
from interview_agent.turn_model import GroqTurnClient, TurnModelError


class FakeStream:
    def __init__(self, parts, delay):
        self.parts, self.delay = parts, delay

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for part in self.parts:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield SimpleNamespace(delta=SimpleNamespace(content=part))


class FakeLLM:
    def __init__(self, parts=("{", "}"), delay=0.0):
        self.parts, self.delay, self.sent = parts, delay, []

    def chat(self, *, chat_ctx, conn_options):
        self.sent.append(([(m.role, m.text_content) for m in chat_ctx.items], conn_options))
        return FakeStream(self.parts, self.delay)


def model_input():
    return compose("turn", "SYSTEM PROMPT", [("answer", [safe_text("트랜잭션 경계를 정리했습니다")])], TurnLlmOut, 400)


def call(llm, timeout=1.0):
    async def main():
        client = GroqTurnClient(model="openai/gpt-oss-120b", timeout=timeout, loop=asyncio.get_running_loop(), llm=llm)
        return await asyncio.to_thread(ask, client, model_input())

    return asyncio.run(main())


def test_it_sends_exactly_the_system_and_the_user_of_the_model_input_and_returns_the_text():
    llm = FakeLLM(parts=('{"answer_type"', ': "dont_know"}'))
    assert call(llm) == '{"answer_type": "dont_know"}'
    messages, options = llm.sent[0]
    mi = model_input()
    assert messages == [("system", mi.system), ("user", mi.user)]
    assert options.max_retry == 0


def test_a_slow_answer_times_out_and_is_cancelled():
    llm = FakeLLM(parts=("a",) * 50, delay=0.05)
    started = time.perf_counter()
    with pytest.raises(TurnModelError) as error:
        call(llm, timeout=0.2)
    assert error.value.code == "timeout" and time.perf_counter() - started < 1.0


def test_an_empty_answer_is_an_error():
    with pytest.raises(TurnModelError) as error:
        call(FakeLLM(parts=("", "  ")))
    assert error.value.code == "empty_output"


def test_the_real_plugin_client_is_built_without_a_network_call():
    async def main():
        return GroqTurnClient(model="openai/gpt-oss-120b", timeout=3.0, loop=asyncio.get_running_loop(), api_key="gsk_test", reasoning_effort="low")

    client = asyncio.run(main())
    assert client.model == "openai/gpt-oss-120b" and type(client._llm).__module__.startswith("livekit.plugins.groq")
