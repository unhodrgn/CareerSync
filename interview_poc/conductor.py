"""The interview flow of the PoC, independent of LiveKit so it can be tested without audio, network or a key.

Code owns the state, the timers and the ending; the model only writes the wording of one follow-up and one closing line.

    greeting (AI disclosure) -> predefined technical question -> candidate answer 1 -> LLM follow-up question
    -> candidate answer 2 -> LLM closing reply -> end

What the LLM may see: a fixed prompt, the predefined question and the candidate's MASKED answers. Nothing else (no
transcript history beyond these, no names, no identifiers). What it writes is screened before anything is spoken; a failed
screen speaks a fixed line. There is no score and no verdict anywhere in the flow.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import Enum

import prompts
from groq_llm import LlmResult, LlmUnavailable
from config import ANSWER_IDLE_SECONDS, HARD_STOP_SECONDS, WRAP_UP_AT_SECONDS
from guards import mask_spoken_pii, screen_closing, screen_followup
from metrics import RunMetrics

log = logging.getLogger("interview_poc.conductor")


class Stage(str, Enum):
    NEW = "new"
    OPENING = "opening"
    WAIT_ANSWER_1 = "wait_answer_1"
    RESPONDING_1 = "responding_1"
    WAIT_ANSWER_2 = "wait_answer_2"
    RESPONDING_2 = "responding_2"
    ENDING = "ending"
    ENDED = "ended"


WAITING = (Stage.WAIT_ANSWER_1, Stage.WAIT_ANSWER_2)


@dataclass(frozen=True)
class SayOutcome:
    delivered: bool
    speech_id: str | None = None


@dataclass
class Hooks:
    """What the flow needs from the outside. LiveKit supplies these in agent.py; tests supply fakes."""

    say: Callable[[str, str, int | None], Awaitable[SayOutcome]]  # (text, step, n): speak and wait until played out
    show: Callable[[str, str, int | None], Awaitable[None]]  # (role, text, n): role agent | candidate | status
    complete: Callable[[str, str], Awaitable[LlmResult]]  # (system prompt, user input)
    end: Callable[[str], Awaitable[None]]  # request the end of the session (idempotent)
    clock: Callable[[], float]


class InterviewConductor:
    def __init__(
        self,
        hooks: Hooks,
        metrics: RunMetrics,
        *,
        names: Iterable[str] = (),
        wrap_up_at: float = WRAP_UP_AT_SECONDS,
        hard_stop: float = HARD_STOP_SECONDS,
        answer_idle: float = ANSWER_IDLE_SECONDS,
    ) -> None:
        self.hooks = hooks
        self.metrics = metrics
        self.names = tuple(names)
        self.wrap_up_at, self.hard_stop, self.answer_idle = wrap_up_at, hard_stop, answer_idle
        self.stage = Stage.NEW
        self.end_reason: str | None = None
        # Masked text only, in memory only: shown on the page, never written anywhere
        self.transcript: list[tuple[str, str]] = []
        self.fallbacks: list[str] = []
        self._followup = ""
        self._answers: list[str] = []
        self._t_start = hooks.clock()
        self._last_activity = self._t_start
        self._candidate_speaking = False

    # ── events from the session ──

    def set_candidate_speaking(self, speaking: bool) -> None:
        self._candidate_speaking = speaking
        self._last_activity = self.hooks.clock()

    async def run_opening(self) -> None:
        self.stage = Stage.OPENING
        for text, step in ((prompts.GREETING, "opening"), (prompts.QUESTION, "question")):
            outcome = await self._speak(text, step)
            if self.stage is not Stage.OPENING:
                return
            if not outcome.delivered:
                log.error("the opening could not be spoken (step=%s)", step)
                await self._end("speech_failed")
                return
        self._wait_for(Stage.WAIT_ANSWER_1)
        await self.hooks.show("status", self.stage.value, None)

    async def on_candidate_turn(self, raw_text: str) -> None:
        """A finished candidate turn (already masked once by the STT node; masked again here, which is idempotent)."""
        if self.stage not in WAITING:
            log.info("candidate turn ignored in stage %s", self.stage.value)
            return
        masked = mask_spoken_pii(raw_text, self.names)
        if not masked.text:
            return
        n = 1 if self.stage is Stage.WAIT_ANSWER_1 else 2
        self.stage = Stage.RESPONDING_1 if n == 1 else Stage.RESPONDING_2  # blocks timers and a second turn at once
        self.metrics.mark("turn_completed", n=n)
        if masked.changed:
            log.info("masked personal data in turn %d: %s", n, masked.kinds)  # kinds and counts only, never the text
        self._answers.append(masked.text)
        self.transcript.append(("candidate", masked.text))
        await self.hooks.show("candidate", masked.text, n)
        if n == 1:
            await self._followup_turn(masked.text)
        else:
            await self._closing_turn(masked.text)

    async def tick(self) -> None:
        """Called about once a second: the time limit and the silence timeout."""
        if self.stage in (Stage.NEW, Stage.ENDING, Stage.ENDED):
            return
        clock = self.hooks.clock()
        if clock - self._t_start >= self.hard_stop:
            await self._end("hard_stop")
        elif self.stage in WAITING and not self._candidate_speaking:
            if clock - self._t_start >= self.wrap_up_at:
                await self._close_with(prompts.TIME_UP_TEXT, "time_up", "time_limit")
            elif clock - self._last_activity >= self.answer_idle:
                await self._close_with(prompts.NO_ANSWER_TEXT, "no_answer", "no_answer")

    async def abort(self, reason: str) -> None:
        """The session is closing for an outside reason (the candidate left): no more speech. Safe to call twice."""
        if self.stage is Stage.ENDED:
            return
        self.stage = Stage.ENDING
        await self._end(reason)

    # ── turns ──

    async def _followup_turn(self, answer: str) -> None:
        try:
            result = await self.hooks.complete(prompts.FOLLOWUP_SYSTEM, prompts.followup_input(prompts.QUESTION, answer))
        except LlmUnavailable as e:
            await self._llm_failed(e)
            return
        self.metrics.mark("llm_done", n=1, ttft_s=result.ttft_s, total_s=result.total_s)
        question = screen_followup(result.text)
        if question is None:
            self.fallbacks.append("followup")
            self.metrics.mark("screen_fallback", step="followup")
            log.warning("follow-up question failed the output screen; speaking the fixed fallback")
            question = prompts.FALLBACK_FOLLOWUP
        self._followup = question
        await self._speak(question, "followup", 1)
        if self.stage is Stage.RESPONDING_1:
            self._wait_for(Stage.WAIT_ANSWER_2)
            await self.hooks.show("status", self.stage.value, None)

    async def _closing_turn(self, answer: str) -> None:
        try:
            result = await self.hooks.complete(
                prompts.CLOSING_SYSTEM, prompts.closing_input(prompts.QUESTION, self._answers[0], self._followup, answer)
            )
        except LlmUnavailable as e:
            await self._llm_failed(e)
            return
        self.metrics.mark("llm_done", n=2, ttft_s=result.ttft_s, total_s=result.total_s)
        line = screen_closing(result.text)
        if line is None:
            self.fallbacks.append("closing")
            self.metrics.mark("screen_fallback", step="closing")
            log.warning("closing reply failed the output screen; speaking the fixed fallback")
            text = prompts.FALLBACK_CLOSING
        else:
            text = f"{line} {prompts.CLOSING_SUFFIX}"
        await self._speak(text, "closing", 2)
        await self._end("completed")

    async def _llm_failed(self, error: LlmUnavailable) -> None:
        # No fallback model: the session says so and ends (the code is safe to log: no key, no prompt)
        log.error("LLM unavailable (%s); ending the session without switching models", error)
        self.metrics.mark("llm_error", code=error.code)
        await self._close_with(prompts.LLM_ERROR_TEXT, "llm_error", f"llm_error:{error.code}")

    # ── helpers ──

    async def _close_with(self, text: str, step: str, reason: str) -> None:
        self.stage = Stage.ENDING
        await self._speak(text, step)
        await self._end(reason)

    async def _speak(self, text: str, step: str, n: int | None = None) -> SayOutcome:
        await self.hooks.show("agent", text, n)
        self.transcript.append(("agent", text))
        outcome = await self.hooks.say(text, step, n)
        if not outcome.delivered:
            log.warning("speech was not fully delivered (step=%s)", step)
        return outcome

    def _wait_for(self, stage: Stage) -> None:
        self.stage = stage
        self._last_activity = self.hooks.clock()

    async def _end(self, reason: str) -> None:
        if self.stage is Stage.ENDED:
            return
        self.stage = Stage.ENDED
        self.end_reason = reason
        self.metrics.finish(reason)
        await self.hooks.end(reason)
