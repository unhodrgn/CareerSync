"""The per-turn model of the Interview Agent: Groq through the LiveKit Groq plugin (M5 S2; docs/DECISIONS.md D52, D62, D80).

The one place in the agent that talks to a model. `GroqTurnClient` has the shape of `ai.llm.client.LLMClient` (`model` and
`complete_json`), so the runner sends a turn only through the engine's flow: `prepare_turn` builds a `ModelInput` from `SafeText`,
`ai.interview.boundary.ask` hands its `system` and `user` to this client, and `parse_turn` checks what comes back. This client sends exactly
those two strings as one system and one user message, nothing else (D62 (B)); it ignores `schema` and `max_tokens`, since `parse_turn` does
the schema check and the token budget is fixed here.

`ask` is synchronous and the plugin is async: the runner calls `ask` in a worker thread, and `complete_json` hands the plugin call back to
the agent's event loop and waits at most `timeout` seconds, then cancels it. It never retries: after a timeout the rules decide (D54, D80).
The Groq plugin is imported with this module, at the top: LiveKit registers a plugin only on the main thread, when the plugin is first imported,
and the worker runs each job off the main thread. `voice.py` imports this module at the top, so the worker registers the plugin when it starts,
before any job (in a job process too: it imports the worker's module on its main thread first). Only the agent's own code imports this module.
`ai/llm/client.py` is not used and not changed, and nothing here imports Anthropic.
"""
import asyncio
import concurrent.futures
import logging

from livekit.agents import APIConnectOptions
from livekit.agents.llm import ChatContext
from livekit.plugins import groq

log = logging.getLogger("interview_agent.turn_model")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"  # the plugin's default, named here so the host is visible in one place
MAX_OUTPUT_TOKENS = 1024  # room for gpt-oss reasoning plus the JSON answer (PoC: groq_llm.py)


class TurnModelError(RuntimeError):
    """The call failed. `code` is safe to log: never the prompt, the answer or the key."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def groq_llm(*, model: str, api_key: str, reasoning_effort: str):
    kwargs = {"base_url": GROQ_BASE_URL, "max_completion_tokens": MAX_OUTPUT_TOKENS}
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    return groq.LLM(model=model, api_key=api_key, **kwargs)


class GroqTurnClient:
    def __init__(self, *, model: str, timeout: float, loop: asyncio.AbstractEventLoop, api_key: str = "", reasoning_effort: str = "", llm=None):
        self.model = model
        self.timeout = timeout
        self._loop = loop
        self._llm = llm if llm is not None else groq_llm(model=model, api_key=api_key, reasoning_effort=reasoning_effort)

    def complete_json(self, system: str, user: str, schema=None, max_tokens: int = 0) -> str:  # noqa: ARG002  (see the module docstring)
        """Called by `ask` in a worker thread, never on the event loop."""
        future = asyncio.run_coroutine_threadsafe(self._complete(system, user), self._loop)
        try:
            return future.result(self.timeout)
        except concurrent.futures.TimeoutError as e:
            future.cancel()
            raise TurnModelError("timeout") from e

    async def _complete(self, system: str, user: str) -> str:
        ctx = ChatContext()
        ctx.add_message(role="system", content=system)
        ctx.add_message(role="user", content=user)
        parts: list[str] = []
        async with self._llm.chat(chat_ctx=ctx, conn_options=APIConnectOptions(max_retry=0, retry_interval=0.1, timeout=self.timeout)) as stream:
            async for chunk in stream:
                delta = chunk.delta
                if delta is not None and delta.content:
                    parts.append(delta.content)
        text = "".join(parts).strip()
        if not text:
            raise TurnModelError("empty_output")
        return text
