"""The conversation around the runner, independent of LiveKit (M5 S4; docs/DECISIONS.md D54, D55, D80).

`VoiceController` is everything the voice worker does that is not audio: it holds the rules of who may talk when, and it calls the runner.
The worker (`voice.py`) gives it three things, so it needs no room, no microphone and no network, and the backend suite runs it against the
real application: `say(text)` (speak a line and wait until it has been played, True if it was), `interrupt()` (stop speaking at once), and
a clock.

- **Opening.** A fixed greeting that says it is an AI and that this is practice (spoken, not stored: it is not one of the engine's turns),
  then `runner.start()`: the first question is stored first and spoken after (store, then speak).
- **One answer at a time.** `submit(text)` takes a masked answer from the transport. While the controller is busy (it is working on an earlier
  answer or speaking) the new one is dropped and counted: an answer spoken over the interviewer is not heard, as in the PoC (the SDK does
  not deliver a turn that ends during uninterruptible speech either).
- **Silence.** `tick()`, called about once a second, hands the engine the seconds of silence since the interviewer's last question or the
  candidate's last word, while nobody is speaking: the engine decides on a nudge, a skip or, when time is short, the wrap-up.
- **Status.** About every `status_poll_seconds` it reads the context (`runner.check()`): a deleted session, one the seeker ended, or one ended
  by a consent withdrawal (D81) stops everything within that time, even while the candidate is silent or speaking.
- **Ending.** The runner posts the one end event; the controller speaks the closing line, if there is one, and finishes. On a stop it
  interrupts the speech, posts nothing, and finishes. `done` is set once, with `outcome`.

Nothing here logs a line of the interview, a name or an answer.
"""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from interview_agent.runner import InterviewRunner, Stopped

log = logging.getLogger("interview_agent.controller")

GREETING = "안녕하세요. 저는 CareerSync의 AI 면접관입니다. 이 모의 면접은 연습용이며 채용 결정에 쓰이지 않습니다. 지금부터 질문을 드리겠습니다."


class VoiceController:
    def __init__(
        self,
        runner: InterviewRunner,
        *,
        say: Callable[[str], Awaitable[bool]],
        interrupt: Callable[[], object] = lambda: None,
        clock: Callable[[], float] = time.monotonic,
        status_poll_seconds: float = 5.0,
        timing=None,
    ) -> None:
        self.runner = runner
        self._say = say
        self._interrupt = interrupt
        self.clock = clock
        self.status_poll_seconds = status_poll_seconds
        self.timing = timing
        self.done = asyncio.Event()
        self.outcome: str | None = None
        self.busy = False
        self.dropped_turns = 0
        self.speech_failures = 0
        self._candidate_speaking = False
        self._silent_since: float | None = None  # None until the opening is over, and while the candidate speaks
        self._last_poll = clock()
        self._tasks: set[asyncio.Task] = set()

    # ── What the transport tells it ──

    def set_candidate_speaking(self, speaking: bool) -> None:
        self._candidate_speaking = speaking
        if self.done.is_set():
            return
        self._silent_since = None if speaking else self.clock()

    def submit(self, text: str) -> bool:
        """A finished answer, masked. True when it is being handled; False when it is dropped (busy, or the interview is over)."""
        if self.done.is_set() or self.busy:
            self.dropped_turns += 1
            if self.timing is not None:
                self.timing.dropped_turns = self.dropped_turns
            return False
        self.busy = True  # synchronously, so that a second answer in the same moment is dropped
        self._spawn(self._turn(text))
        return True

    async def run_opening(self) -> None:
        self.busy = True
        try:
            if self.timing is not None:
                self.timing.reply_handed_to_speech(opening=True)
            await self._speak_one(GREETING)
            lines = await self.runner.start()
            await self._speak(lines)
        except Stopped as stop:
            await self._stopped(stop.reason)
        except Exception as error:  # noqa: BLE001  (only the type is logged)
            await self._failed(error)
        finally:
            self.busy = False
            self._rearm_silence()

    async def tick(self) -> None:
        """About once a second: the status poll, then the silence."""
        if self.done.is_set() or self.runner.engine is None:
            return
        now = self.clock()
        if now - self._last_poll >= self.status_poll_seconds:
            self._last_poll = now
            try:
                await self.runner.check()
            except Stopped as stop:
                await self._stopped(stop.reason)
                return
        if self.busy or self._candidate_speaking or self._silent_since is None or self.runner.finished:
            return
        self.busy = True
        try:
            lines = await self.runner.silence(now - self._silent_since)
            if lines:
                if self.timing is not None:
                    self.timing.reply_handed_to_speech(nudge=True)
                await self._speak(lines)
        except Stopped as stop:
            await self._stopped(stop.reason)
        except Exception as error:  # noqa: BLE001
            await self._failed(error)
        finally:
            self.busy = False

    async def candidate_left(self, reason: str = "candidate_left") -> None:
        """The candidate went away, or the transport closed (`session_closed:<why>`): the runner posts the aborted end, nothing is spoken."""
        if self.done.is_set():
            return
        try:
            await self.runner.leave(reason)
        except Stopped as stop:
            await self._stopped(stop.reason)
            return
        except Exception as error:  # noqa: BLE001
            await self._failed(error)
            return
        await self.finish(self.runner.stopped or "aborted")

    async def finish(self, outcome: str) -> None:
        """Idempotent: the first outcome stays. Cancels what is still running, except the caller."""
        if self.outcome is None:
            self.outcome = outcome
        self.done.set()
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current and not task.done():
                task.cancel()

    # ── Inside ──

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _rearm_silence(self) -> None:
        if not self.done.is_set() and not self._candidate_speaking:
            self._silent_since = self.clock()

    async def _turn(self, text: str) -> None:
        calls_before = len(self.runner.timings)
        try:
            lines = await self.runner.answer(text)
            if self.timing is not None:
                self.timing.runner_done(self.runner.timings[-1] if len(self.runner.timings) > calls_before else None)
                if lines:
                    self.timing.reply_handed_to_speech()
            await self._speak(lines)
        except Stopped as stop:
            await self._stopped(stop.reason)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            await self._failed(error)
        finally:
            self.busy = False
            self._rearm_silence()

    async def _speak(self, lines: list[str]) -> None:
        for line in lines:
            if self.done.is_set():
                return
            await self._speak_one(line)
        if self.runner.finished and not self.done.is_set():
            await self.finish(self.runner.stopped or "aborted")  # the closing line, if any, was the last of `lines`

    async def _speak_one(self, text: str) -> None:
        if not await self._say(text):
            self.speech_failures += 1
            if self.timing is not None:
                self.timing.speech_failures = self.speech_failures

    async def _stopped(self, reason: str) -> None:
        self._interrupt()
        await self.finish(reason)

    async def _failed(self, error: Exception) -> None:
        log.error("the voice interview failed (%s)", type(error).__name__)
        try:
            await self.runner.leave("agent_error")
        except Exception:  # noqa: BLE001
            pass
        self._interrupt()
        await self.finish("agent_error")
