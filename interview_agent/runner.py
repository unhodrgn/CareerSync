"""The interview loop of the Interview Agent, independent of the transport (M5 S2; docs/DECISIONS.md D54, D56, D58, D62, D79).

The engine of `ai/interview/` makes every decision; the runner carries: it reads the session's context, runs the engine over the plan the
backend stored, posts every line and answer to the internal API, and hands back the lines to speak. The text driver (`text_cli.py`) and
the voice worker (stage S4) both drive it: text in, lines out.

Rules it keeps:

- **Store, then speak.** `start`, `answer` and `silence` post the new turns first and return the interviewer's lines only once the
  backend took them. A refused post means nothing more is said.
- **One end event.** When the engine ends (`ended`: plan done or time, with the closing line) or is aborted (`leave`, an agent error), the
  runner posts exactly one end event, the closing line only with `ended`. A session that never started (no turn stored) gets none: the
  backend cannot end a `created` session, and it reads as `not_joined` after the join deadline.
- **Stop.** A 404 (deleted, expired, or not this room), or `INTERVIEW_ALREADY_ENDED` / `INTERVIEW_NOT_ACTIVE` (ended by the seeker, time
  over): `Stopped` is raised and nothing more is posted. A permanent refusal (a 422, a conflict) or a backend that stays unreachable after
  the client's retries: the runner tries to post an `aborted` end with the reason `agent_error`, then stops. `check()` is the status poll
  (about every 5 s in the voice worker, D79 (6)).
- **The model** (D52, D79 (5)): only through the engine's flow, `prepare_turn` → `ask` → `parse_turn`, with the per-turn timeout (default
  3 s, never above the session's `turn_llm_deadline_seconds`). A timeout, an error or a rejected answer means the rules for that turn (D54);
  only the outcome and the time are logged, never a text.
- **Consent withdrawal** (D80, Q39). When the seeker withdraws the AI consent, the backend ends the session (`consent_withdrawn`), so the
  next post is refused and the status check stops the runner like any other end. In the model mode the runner also reads the context right
  before every model call (one attempt, no retry): a session that is no longer active stops it; a seeker without the current AI consent
  whose session is still active (the moment between two statements) makes it post an aborted end (`session_closed:consent_withdrawn`) and
  stop; a context it cannot read means no model call for that turn (the rules decide). A model call that started before the withdrawal
  may finish, but its answer is refused when posted, so nothing of it is stored. The rules mode makes no inference and needs no check.
- **Personal data.** The engine masks every answer (with the seeker's display name from the context) before it is stored, posted or shown
  to a model; the name lives in the engine's memory only and is never logged or posted (D79 (3)). The backend masks again before storing.
"""
import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

from ai.guardrails.blocklist import load_blocklist
from ai.interview import InterviewEngine, InterviewLimits, InterviewPlan, ask, coverage_snapshot, parse_turn, prepare_turn
from ai.interview.types import Phase

from interview_agent.backend_client import Ended, Gone, Refused, SeqGap, SessionClient, Transient

log = logging.getLogger("interview_agent.runner")

# The criteria guardrail, then the interview blocklist: the backend's `career_service.interview_blocklists()`, read from the same files
BLOCKLIST_FILES = ("blocklist.yaml", "interview_blocklist.yaml")
FINAL = (Phase.ENDED, Phase.ABORTED)
ACTIVE = ("created", "live")
CONSENT_WITHDRAWN = "consent_withdrawn"  # the backend's end reason (D80), and the reason this runner stops with


class Stopped(Exception):
    """The runner stopped and posts nothing more. `reason`: completed, aborted, gone, ended_elsewhere, consent_withdrawn, refused, unreachable,
    not_joinable, plan_mismatch."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def load_blocklists(data_dir: Path) -> list:
    return [load_blocklist(data_dir / name) for name in BLOCKLIST_FILES]


class InterviewRunner:
    def __init__(self, client: SessionClient, *, data_dir: Path, model=None, llm_timeout: float = 3.0, clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.data_dir = data_dir
        self.model = model  # an LLMClient-shaped object (turn_model.GroqTurnClient), or None for the rules
        self.llm_timeout = llm_timeout
        self.clock = clock
        self.engine: InterviewEngine | None = None
        self.names: tuple[str, ...] = ()  # the seeker's display name from the context: in memory only, for masking (D79 (3)); never logged or posted
        self.stopped: str | None = None
        self.timings: list[tuple[str, float]] = []  # (outcome, seconds) of each model call, for the latency report
        self._plan: InterviewPlan | None = None
        self._t0: float | None = None
        self._sent = 0  # engine turns already handled
        self._posted: dict[int, dict] = {}  # seq -> the body the backend took, to repair a sequence gap

    @property
    def finished(self) -> bool:
        return self.stopped is not None

    # ── The interview ──

    async def open(self) -> None:
        """Read the context and build the engine. `Stopped` unless the session is `created`, joinable and empty, with a plan the engine runs
        unchanged."""
        context = await self._read_context()
        if context.get("status") != "created" or not context.get("joinable") or context.get("last_seq"):
            raise self._stop("not_joinable")
        plan = InterviewPlan.from_dict(context["plan"])
        limits = InterviewLimits(**context["limits"])
        self.names = tuple(context.get("mask_names") or ())
        engine = InterviewEngine(plan, blocklists=load_blocklists(self.data_dir), limits=limits, names=list(self.names))
        if engine.plan_issues:  # the stored plan is a fixed point of validation; another plan would shift the item indexes
            raise self._stop("plan_mismatch")
        self.engine, self._plan = engine, plan
        self.llm_timeout = min(self.llm_timeout, float(limits.turn_llm_deadline_seconds))

    async def start(self) -> list[str]:
        """The first question (stored as seq 1, which starts the session). Speak the greeting and the AI disclosure before it."""
        self._require_running()
        self._t0 = self.clock()
        self.engine.start()
        return await self._flush()

    async def answer(self, text: str) -> list[str]:
        """One finished answer, as transcribed (the engine masks it). The interviewer's next lines, already stored."""
        self._require_running()
        now = self._now()
        analysis = await self._analysis(text)
        self.engine.on_answer(text, now, analysis)
        return await self._flush()

    async def silence(self, seconds: float) -> list[str]:
        """The candidate has said nothing for `seconds`: a nudge, a skip, or nothing yet."""
        self._require_running()
        if self.engine.on_silence(seconds, self._now()) is None:
            return []
        return await self._flush()

    async def leave(self, reason: str = "candidate_left") -> None:
        """The candidate left, or the transport closed: post the aborted end. Nothing to post if nothing was stored yet."""
        if self.finished or self.engine is None:
            return
        if self._t0 is None:
            self.stopped = reason
            return
        self.engine.abort(reason, self._now())
        await self._flush()

    async def check(self) -> dict | None:
        """The status poll: `Stopped` when the session is gone or no longer active; None when the backend did not answer (try again later)."""
        try:
            context = await self.client.context(retry=False)
        except Transient:
            return None
        except Gone:
            raise self._stop("gone") from None
        except (Ended, Refused, SeqGap):
            raise self._stop("refused") from None
        if context.get("status") not in ACTIVE:
            raise self._stop(CONSENT_WITHDRAWN if context.get("end_reason") == CONSENT_WITHDRAWN else "ended_elsewhere")
        return context

    # ── Internals ──

    def _now(self) -> float:
        return self.clock() - (self._t0 if self._t0 is not None else self.clock())

    def _require_running(self) -> None:
        if self.engine is None:
            raise RuntimeError("open() first")
        if self.finished:
            raise Stopped(self.stopped)

    def _stop(self, reason: str) -> Stopped:
        self.stopped = reason
        log.info("runner stopped: %s", reason)
        return Stopped(reason)

    async def _read_context(self) -> dict:
        try:
            return await self.client.context()
        except Gone:
            raise self._stop("gone") from None
        except Transient:
            raise self._stop("unreachable") from None
        except (Ended, Refused, SeqGap):
            raise self._stop("refused") from None

    async def _analysis(self, text: str):
        if self.model is None:
            return None
        request = prepare_turn(self.engine, text)
        if request is None:  # the rules decide this answer (empty, very short, a request to repeat): no model is asked
            return None
        if not await self._may_ask_the_model():
            return None
        started = time.perf_counter()
        raw, outcome = None, "ok"
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(ask, self.model, request.model_input), self.llm_timeout)
        except TimeoutError:
            outcome = "timeout"
        except Exception as e:  # noqa: BLE001  (every failure means the rules; only the type is logged, never a text)
            outcome = f"error:{type(e).__name__}"
        analysis = None
        if raw is not None:
            turn = parse_turn(request, raw, method=f"llm:{self.model.model}")
            analysis = turn.analysis
            if analysis is None:
                outcome = f"rejected:{turn.reason}"
        elapsed = time.perf_counter() - started
        self.timings.append((outcome, elapsed))
        log.info("turn analysis: %s in %.2f s", outcome, elapsed)
        return analysis

    async def _may_ask_the_model(self) -> bool:
        """The check right before a model call (D80). `Stopped` when the session is gone or no longer active (the withdrawal itself ends it);
        an aborted end and `Stopped` when it is active but the seeker has no current AI consent; False (the rules decide this turn) when the
        context cannot be read, because the consent cannot be shown to stand."""
        context = await self.check()
        if context is None:
            log.warning("turn analysis: the context could not be read; no model call, the rules decide")
            return False
        if not context.get("ai_consent"):
            await self.leave(f"session_closed:{CONSENT_WITHDRAWN}")
            self.stopped = CONSENT_WITHDRAWN
            raise Stopped(CONSENT_WITHDRAWN)
        return True

    def _event_turn(self, turn, coverage: dict | None) -> dict:
        items = self._plan.items
        index = turn.item_index
        topic = items[index].topic_id if turn.kind != "closing" and index is not None and 0 <= index < len(items) else None
        return {
            "seq": turn.seq, "role": turn.role, "kind": turn.kind, "item_index": index, "topic_id": topic, "text": turn.text,
            "method": turn.method, "analysis": turn.analysis, "masked_kinds": turn.masked_kinds, "coverage": coverage,
        }

    async def _flush(self) -> list[str]:
        state = self.engine.state
        # A turn event always says `listening` with no end reason, even when this call ended the interview: the end event carries the final
        # phase and reason (interview_ingest_service).
        coverage = coverage_snapshot(state) | {"phase": "listening", "end_reason": None}
        lines: list[str] = []
        closing = None
        for turn in state.turns[self._sent :]:
            if turn.kind == "closing":
                closing = turn
                continue
            await self._post({"type": "turn", "turn": self._event_turn(turn, coverage)}, turn.seq)
            if turn.role == "agent":
                lines.append(turn.text)
        self._sent = len(state.turns)
        if state.phase in FINAL:
            body = {"type": "end", "coverage": coverage_snapshot(state), "closing": self._event_turn(closing, None) if closing is not None else None}
            await self._post(body, None)
            if closing is not None:
                lines.append(closing.text)
            self.stopped = "completed" if state.phase is Phase.ENDED else "aborted"
        return lines

    async def _post(self, body: dict, seq: int | None) -> dict:
        try:
            try:
                result = await self.client.post_event(body)
            except SeqGap as gap:
                await self._resend_from(gap, seq)
                result = await self.client.post_event(body)
        except Gone:
            raise self._stop("gone") from None
        except Ended:
            raise self._stop("ended_elsewhere") from None
        except (Refused, Transient, SeqGap) as error:
            log.warning("event refused (%s); ending the session", error.code)
            if body["type"] == "turn":
                await self._abort_after_error()
            raise self._stop("unreachable" if isinstance(error, Transient) else "refused") from None
        if seq is not None:
            self._posted[seq] = body
        return result

    async def _resend_from(self, gap: SeqGap, seq: int | None) -> None:
        """Post again the events the backend lacks, from the one it expects up to this one; otherwise the gap is permanent."""
        expected = gap.expected
        if seq is None or expected is None or expected >= seq or any(s not in self._posted for s in range(expected, seq)):
            raise gap
        for s in range(expected, seq):
            await self.client.post_event(self._posted[s])

    async def _abort_after_error(self) -> None:
        """Best effort: the aborted end with `agent_error`. The coverage the engine has may claim an answer the backend refused, and then the
        end is refused too; the session then reads `aborted` (`stale_live`) once its deadline and grace are over."""
        self.engine.abort("agent_error", self._now())
        body = {"type": "end", "coverage": coverage_snapshot(self.engine.state), "closing": None}
        try:
            await self.client.post_event(body)
        except Exception as e:  # noqa: BLE001  (already stopping; only the type is logged)
            log.warning("the aborted end was not stored either (%s)", type(e).__name__)
