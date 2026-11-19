"""Ingestion of the turns and the end of a practice interview (M4 S3a; docs/DECISIONS.md D53, D54, D57, D61–D63).

The Interview Agent (M5) runs the engine and posts what it says and hears; this module validates and stores it. There is no
HTTP endpoint yet, and the functions take a session id and no user: the endpoint that calls them (M5) must authenticate the agent
and bind it to the session. Nothing here is reachable from a seeker or a company.

What is trusted, and what is not. The agent is the source of the coverage (the status of each topic, the rubric levels) and of the
words: this module checks their shape, their relation to the persisted canonical plan and the engine's rules, and the clock, and
stores them. It never works out a status, never upgrades one, and never reads a candidate's answer to decide what it showed. A
buggy or compromised agent can still forge statuses and lines; the checks narrow that and cannot remove it.

**Turns** (`record_turn`). Pure validation first, nothing written: the plan is the stored canonical one (its digest is checked),
the event has the right types, role and kind, an item index into the plan, and the echo of the topic id at that index; the text is
masked again here (candidate and agent alike), is at most 4000 masked characters, and a candidate's quotes are verified against
the masked answer again (a quote that is not in it is dropped). The analysis is checked and stored but never changes the coverage.
Then: a stored turn with the same sequence number and the same identity (role, kind, item index, masked text) is a duplicate
and nothing is written; a different one is a conflict and the first write stays. Then the lifecycle, by the backend's clock at the
moment of receipt: the first turn of a `created` session starts it; a `live` session takes turns until `active_until`, 600 seconds
after its start, and not one after that. Then one transaction (see `_store_turn`).

**End** (`record_end`). One final coverage snapshot (phase `ended` or `aborted`) and, only for `ended`, the closing line. Accepted
until `active_until` + the grace (30 seconds): the grace is for this event alone, and a turn is refused in it. The status
change, the final coverage and the closing line are one transaction. A retry with the same payload is a duplicate; any other
payload for a session that is over is `INTERVIEW_ALREADY_ENDED`.

**Concurrency** is compare-and-set. Each write starts with a guard UPDATE that checks the status and the deadline in the same
statement that takes the row lock (PostgreSQL), so a turn, an end, the seeker's End and `settle` cannot all win; the checks
that need the stored state (the last sequence number, the previous coverage, the answers) are read after it, under that
lock. `UNIQUE (session_id, seq)` stays as a backstop. No model is called here, so the lock lasts a few statements. The behaviour
under real parallel requests has been written as PostgreSQL-only tests; a run on SQLite proves none of it.

**Coverage rules** (`STATUS_TRANSITIONS`, `_check_coverage_state`) are the ones the real engine obeys; a test drives the real engine
through scripted and randomized interviews and fails if it ever produces a transition outside the table, or if a table entry is
never produced.
"""
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai.interview import AnswerType, InterviewPlan, TopicStatus, mask_spoken, verified_quotes
from ai.interview.types import LEVEL_RANK
from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn, User
from app.models.interview import InterviewStatus
from app.services.interview_plan_service import plan_digest
from app.services.interview_time import Clock, derive, now_from, utcnow

log = logging.getLogger(__name__)

_S = InterviewSession.__table__
_T = InterviewTurn.__table__

AGENT_KINDS = frozenset({"question", "follow_up", "clarify", "repeat", "redirect", "nudge"})
ROLE_KINDS = {"agent": AGENT_KINDS, "candidate": frozenset({"answer"})}
CLOSING = "closing"  # only inside the end event
LISTENING = "listening"
END_PHASES = frozenset({"ended", "aborted"})
STATUSES = frozenset(s.value for s in TopicStatus)
LEVELS = frozenset(LEVEL_RANK)
ANSWER_TYPES = frozenset(a.value for a in AnswerType)

# What a topic's status may do between two snapshots, from what the engine does (`InterviewEngine`): it is asked, then each
# answer re-derives it from the best level of every rubric point (so it only improves), and a silence or a skip decision ends
# it as `skipped`. Checked against the real engine by test_interview_ingest_coverage.py; never produced, so not allowed:
# not_asked -> skipped (the engine's own screen of a question is the one validation applies to the plan), and every step back.
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_asked": frozenset({"not_asked", "asked"}),
    "asked": frozenset({"asked", "demonstrated", "partial", "not_shown", "skipped"}),
    "partial": frozenset({"partial", "demonstrated", "skipped"}),
    "not_shown": frozenset({"not_shown", "partial", "demonstrated", "skipped"}),
    "demonstrated": frozenset({"demonstrated", "skipped"}),
    "skipped": frozenset({"skipped"}),
}
# Statuses that only an answer can produce, so the topic must have a stored candidate answer
NEEDS_ANSWER = frozenset({"demonstrated", "partial", "not_shown"})

# The reasons an interview can end with. Anything else (the PoC's `session_closed:<reason>` keeps its part before the colon) is
# stored as `agent_ended`: a free-form string from the agent is never persisted.
END_REASONS = frozenset({"plan_exhausted", "empty_plan", "time", "candidate_left", "session_closed", "agent_error", "agent_ended"})
DEFAULT_END_REASON = "agent_ended"

_METHOD = re.compile(r"^(?:rules|llm:[\w.:/\-]{1,80})$")
_KIND_KEY = re.compile(r"^[a-z_]{1,20}$")
_MAX_MASKED_KINDS, _MAX_COUNT = 10, 1000
_MAX_QUOTES_IN, _MAX_QUOTE_IN_CHARS = 10, 500
_MAX_TOPICS, _MAX_POINTS = 64, 32


# ── What comes in, and what goes back ──


@dataclass(frozen=True)
class TurnEvent:
    seq: int
    role: str  # "agent" | "candidate"
    kind: str  # agent: question, follow_up, clarify, repeat, redirect, nudge; candidate: answer; the closing line: "closing"
    item_index: int | None
    topic_id: str | None  # the echo of the plan's topic at item_index: checked, never stored
    text: str
    method: str = "rules"
    analysis: Mapping | None = None  # a candidate's TurnAnalysis.to_dict(): answer_type, points, quotes, method
    masked_kinds: Mapping | None = None  # kinds of data the agent masked, counts only
    coverage: Mapping | None = None  # coverage_snapshot(state) after this turn; required for a turn, none for the closing line


@dataclass(frozen=True)
class EndEvent:
    coverage: Mapping  # the final coverage_snapshot(state): phase "ended" or "aborted"
    closing: TurnEvent | None = None  # role agent, kind "closing"; only with phase "ended"


@dataclass(frozen=True)
class TurnResult:
    outcome: str  # "stored" | "duplicate"
    seq: int
    started: bool  # this turn started the session
    dropped_quotes: int  # quotes that were not in the masked answer


@dataclass(frozen=True)
class EndResult:
    outcome: str  # "ended" | "duplicate"
    status: str  # "completed" | "aborted"
    end_reason: str


@dataclass(frozen=True)
class _Plan:
    topic_ids: tuple[str, ...]
    rubric: tuple[frozenset[str], ...]  # the rubric point ids of each item


@dataclass(frozen=True)
class _Turn:  # a turn event that passed the pure validation
    seq: int
    role: str
    kind: str
    item_index: int | None
    text: str  # masked
    method: str
    analysis: dict | None
    masked_kinds: dict
    dropped_quotes: int
    coverage: dict | None

    @property
    def identity(self) -> tuple:
        return (self.role, self.kind, self.item_index, self.text)


@dataclass(frozen=True)
class _End:
    status: str
    end_reason: str
    coverage: dict
    closing: _Turn | None


# ── Errors: codes in `extra`, never any text of the event ──


def _bad(field: str) -> AppError:
    log.info("interview turn refused: %s", field)
    return AppError(422, "INTERVIEW_BAD_TURN", "면접 이벤트가 올바르지 않습니다.", field=field)


def _bad_coverage(field: str) -> AppError:
    log.info("interview coverage refused: %s", field)
    return AppError(422, "INTERVIEW_BAD_COVERAGE", "면접 진행 상태가 올바르지 않습니다.", field=field)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ── Record a turn ──


def record_turn(db: Session, session_id: int, event: TurnEvent, *, clock: Clock = utcnow) -> TurnResult:
    """Validate and store one turn. `stored`, or `duplicate` (the same event again: nothing written, the coverage untouched)."""
    now = now_from(clock)
    try:
        row = _find(db, session_id, now)
        plan = _load_plan(row)
        turn = _clean_turn(event, plan, _names(db, row.seeker_id), closing=False)
        if _is_duplicate(db, session_id, turn):  # after the plan and the topic echo are checked, before the lifecycle
            db.rollback()
            return TurnResult("duplicate", turn.seq, False, 0)
        eff = derive(row.status, row.end_reason, row.ended_at, row.active_until, now, settings.INTERVIEW_END_GRACE_SECONDS)
        first = row.status == InterviewStatus.CREATED
        if first:
            if not eff.joinable:
                raise _not_active(eff)
            if not (turn.seq == 1 and turn.role == "agent" and turn.kind == "question" and turn.item_index == 0):
                raise _bad("first_turn")  # a session starts with the engine's first question
        elif row.status != InterviewStatus.LIVE or not eff.accepting_turns:
            raise _not_active(eff)  # past the 600 seconds no turn is accepted, the grace is for the end event
        return _store_turn(db, row, plan, turn, now, first)
    except BaseException:
        db.rollback()
        raise


def _store_turn(db: Session, row: InterviewSession, plan: _Plan, turn: _Turn, now, first: bool) -> TurnResult:
    """One transaction. The guard UPDATE is the lifecycle check, the row lock and (for the first turn) the start; the rest is
    read under that lock."""
    session_id = row.id
    guard = update(_S).where(_S.c.id == session_id, _S.c.expires_at > now)
    if first:
        guard = guard.where(_S.c.status == InterviewStatus.CREATED, _S.c.active_until >= now).values(
            status=InterviewStatus.LIVE, started_at=now, active_until=now + timedelta(seconds=_max_seconds(row))
        )
    else:
        guard = guard.where(_S.c.status == InterviewStatus.LIVE, _S.c.active_until >= now).values(status=_S.c.status)
    if db.execute(guard).rowcount != 1:  # started by the same event meanwhile, or ended, settled, deleted, past the deadline
        db.rollback()
        if _is_duplicate(db, session_id, turn):
            db.rollback()
            return TurnResult("duplicate", turn.seq, False, 0)
        raise _not_active_now(db, session_id, now)
    last, previous, answered = _stored_state(db, session_id)
    if turn.seq <= last:  # another request stored this sequence number between the pre-check and the guard
        if _is_duplicate(db, session_id, turn):
            db.rollback()
            return TurnResult("duplicate", turn.seq, False, 0)
    if turn.seq != last + 1:
        raise AppError(409, "INTERVIEW_SEQ_GAP", "이전 이벤트가 누락되었습니다.", expected_seq=last + 1)
    if turn.role == "candidate" and turn.item_index is not None:
        answered = answered | {turn.item_index}
    _check_coverage_state(previous, turn.coverage, plan, answered)
    db.execute(update(_S).where(_S.c.id == session_id).values(coverage=turn.coverage))
    try:
        _insert_turn(db, session_id, turn, now)
    except IntegrityError:
        db.rollback()  # UNIQUE (session_id, seq): a concurrent request stored this sequence number first
        if _is_duplicate(db, session_id, turn):
            db.rollback()
            return TurnResult("duplicate", turn.seq, False, 0)
        raise
    db.commit()
    return TurnResult("stored", turn.seq, first, turn.dropped_quotes)


# ── Record the end ──


def record_end(db: Session, session_id: int, event: EndEvent, *, clock: Clock = utcnow) -> EndResult:
    """Validate and store the final event of an interview: `ended`, or `duplicate` (the same payload again)."""
    now = now_from(clock)
    try:
        row = _find(db, session_id, now)
        plan = _load_plan(row)
        end = _clean_end(event, plan, _names(db, row.seeker_id))
        if row.status in (InterviewStatus.COMPLETED, InterviewStatus.ABORTED):
            return _end_of_a_finished_session(db, row, end)
        eff = derive(row.status, row.end_reason, row.ended_at, row.active_until, now, settings.INTERVIEW_END_GRACE_SECONDS)
        if row.status != InterviewStatus.LIVE or not (eff.accepting_turns or eff.end_grace_open):
            raise _not_active(eff)
        return _store_end(db, row, plan, end, now)
    except BaseException:
        db.rollback()
        raise


def _store_end(db: Session, row: InterviewSession, plan: _Plan, end: _End, now) -> EndResult:
    """One transaction: the guard UPDATE, the checks under its lock, the status change with the final coverage, the closing line."""
    session_id = row.id
    grace = timedelta(seconds=settings.INTERVIEW_END_GRACE_SECONDS)
    guard = (
        update(_S)
        .where(_S.c.id == session_id, _S.c.expires_at > now, _S.c.status == InterviewStatus.LIVE, _S.c.active_until >= now - grace)
        .values(status=_S.c.status)
    )
    if db.execute(guard).rowcount != 1:
        db.rollback()
        fresh = _find(db, session_id, now)
        if fresh.status in (InterviewStatus.COMPLETED, InterviewStatus.ABORTED):
            return _end_of_a_finished_session(db, fresh, end)
        raise _not_active_now(db, session_id, now)
    last, previous, answered = _stored_state(db, session_id)
    if end.closing is not None:
        if end.closing.seq <= last:
            raise AppError(409, "INTERVIEW_SEQ_CONFLICT", "같은 순번에 다른 내용이 이미 저장되어 있습니다.", seq=end.closing.seq)
        if end.closing.seq != last + 1:
            raise AppError(409, "INTERVIEW_SEQ_GAP", "이전 이벤트가 누락되었습니다.", expected_seq=last + 1)
    _check_coverage_state(previous, end.coverage, plan, answered)
    changed = db.execute(
        update(_S)
        .where(_S.c.id == session_id, _S.c.status == InterviewStatus.LIVE)
        .values(status=end.status, end_reason=end.end_reason, ended_at=now, active_until=None, coverage=end.coverage)
    ).rowcount
    if changed != 1:  # cannot happen under the lock; refuse rather than write a closing line without the status change
        raise _not_active_now(db, session_id, now)
    if end.closing is not None:
        _insert_turn(db, session_id, end.closing, now)
    db.commit()
    return EndResult("ended", end.status, end.end_reason)


def _end_of_a_finished_session(db: Session, row: InterviewSession, end: _End) -> EndResult:
    """The session is over. The same final event again is a duplicate; anything else, including a different closing line, is not."""
    stored = db.execute(
        select(_T.c.role, _T.c.kind, _T.c.item_index, _T.c.text).where(_T.c.session_id == row.id, _T.c.kind == CLOSING)
    ).first()
    same = (
        row.status == end.status
        and row.end_reason == end.end_reason
        and row.coverage == end.coverage
        and ((stored is None and end.closing is None) or (stored is not None and end.closing is not None and tuple(stored) == end.closing.identity))
    )
    db.rollback()
    if same:
        return EndResult("duplicate", end.status, end.end_reason)
    log.warning("interview end refused: the session is already over with a different payload")
    raise AppError(409, "INTERVIEW_ALREADY_ENDED", "이미 종료된 면접입니다.", status=row.status)


# ── Finding the session, the plan and the stored state ──


def _find(db: Session, session_id: int, now) -> InterviewSession:
    row = db.scalars(
        select(InterviewSession).where(InterviewSession.id == session_id, InterviewSession.expires_at > now).execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise AppError(404, "INTERVIEW_NOT_FOUND", "모의 면접을 찾을 수 없습니다.")
    return row


def _load_plan(row: InterviewSession) -> _Plan:
    """The persisted canonical plan, only if it is the one that was stored: the digest must match. Otherwise nothing is accepted."""
    invalid = AppError(409, "INTERVIEW_PLAN_INVALID", "면접 계획을 확인할 수 없습니다.")
    if not isinstance(row.plan, dict) or not row.plan_sha256 or plan_digest(row.plan) != row.plan_sha256:
        raise invalid
    try:
        plan = InterviewPlan.from_dict(row.plan)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise invalid from None
    if not plan.items:
        raise invalid
    return _Plan(tuple(i.topic_id for i in plan.items), tuple(frozenset(p.id for p in i.rubric) for i in plan.items))


def _names(db: Session, seeker_id: int) -> list[str]:
    """The seeker's display name, only to mask it in what was said. It is never stored or returned."""
    name = db.scalar(select(User.display_name).where(User.id == seeker_id))
    return [name] if name and name.strip() else []


def _max_seconds(row: InterviewSession) -> int:
    value = row.limits.get("max_seconds") if isinstance(row.limits, dict) else None
    return value if _is_int(value) and value > 0 else settings.INTERVIEW_MAX_SECONDS


def _stored_state(db: Session, session_id: int) -> tuple[int, dict | None, set[int]]:
    """(the last sequence number, the stored coverage, the item indexes with a candidate answer), read under the guard's lock."""
    last = db.scalar(select(func.coalesce(func.max(_T.c.seq), 0)).where(_T.c.session_id == session_id)) or 0
    previous = db.scalar(select(_S.c.coverage).where(_S.c.id == session_id))
    answered = set(
        db.scalars(select(_T.c.item_index).where(_T.c.session_id == session_id, _T.c.role == "candidate", _T.c.item_index.is_not(None)).distinct())
    )
    return last, previous if isinstance(previous, dict) else None, answered


def _is_duplicate(db: Session, session_id: int, turn: _Turn) -> bool:
    """True when this sequence number holds the same turn; a conflict (409) when it holds another one; False when it is free."""
    stored = db.execute(select(_T.c.role, _T.c.kind, _T.c.item_index, _T.c.text).where(_T.c.session_id == session_id, _T.c.seq == turn.seq)).first()
    if stored is None:
        return False
    if tuple(stored) == turn.identity:
        return True
    log.warning("interview turn conflict at seq %d: the first write stays", turn.seq)
    raise AppError(409, "INTERVIEW_SEQ_CONFLICT", "같은 순번에 다른 내용이 이미 저장되어 있습니다.", seq=turn.seq)


def _insert_turn(db: Session, session_id: int, turn: _Turn, now) -> None:
    db.execute(
        insert(_T).values(
            session_id=session_id,
            seq=turn.seq,
            role=turn.role,
            kind=turn.kind,
            item_index=turn.item_index,
            text=turn.text,
            method=turn.method,
            analysis=turn.analysis,
            masked_kinds=turn.masked_kinds,
            created_at=now,
        )
    )


def _not_active(eff) -> AppError:
    return AppError(409, "INTERVIEW_NOT_ACTIVE", "진행 중인 면접이 아닙니다.", status=eff.status, end_grace_open=eff.end_grace_open)


def _not_active_now(db: Session, session_id: int, now) -> AppError:
    try:
        row = _find(db, session_id, now)
    except AppError as gone:
        return gone
    eff = derive(row.status, row.end_reason, row.ended_at, row.active_until, now, settings.INTERVIEW_END_GRACE_SECONDS)
    return _not_active(eff)


# ── Validation of a turn event (pure: nothing is written) ──


def _clean_turn(event: TurnEvent, plan: _Plan, names: list[str], *, closing: bool) -> _Turn:
    if not isinstance(event, TurnEvent):
        raise _bad("event")
    if not _is_int(event.seq) or event.seq < 1:
        raise _bad("seq")
    if event.seq > (settings.INTERVIEW_MAX_TURNS if closing else settings.INTERVIEW_MAX_TURNS - 1):
        raise AppError(409, "INTERVIEW_TURN_LIMIT", "저장할 수 있는 발화 수를 넘었습니다.")
    if closing:
        if event.role != "agent" or event.kind != CLOSING:
            raise _bad("kind")
    elif event.role not in ROLE_KINDS or event.kind not in ROLE_KINDS[event.role]:
        raise _bad("kind")  # includes "closing": the closing line goes with the end event only
    index = event.item_index
    if closing:
        if index is not None and not (_is_int(index) and 0 <= index <= len(plan.topic_ids)):
            raise _bad("item_index")  # after the last item the engine's index is len(items)
    elif not (_is_int(index) and 0 <= index < len(plan.topic_ids)):
        raise _bad("item_index")
    expected_topic = plan.topic_ids[index] if index is not None and index < len(plan.topic_ids) else None
    # The engine's closing action has no topic whatever the index, so the closing line may echo None; every other turn echoes the topic
    if event.topic_id != expected_topic and not (closing and event.topic_id is None):
        raise _bad("topic_id")  # the agent runs another plan than the stored one
    if not isinstance(event.text, str) or "\x00" in event.text:
        raise _bad("text")  # U+0000 is refused, never stripped: PostgreSQL TEXT cannot hold it, and a text that has one is not a transcript
    if len(event.text) > settings.INTERVIEW_MAX_RAW_TURN_CHARS:
        raise AppError(422, "INTERVIEW_TURN_TOO_LONG", "발화가 너무 깁니다.")
    masked = mask_spoken(event.text, names)
    if len(masked.text) > settings.INTERVIEW_MAX_TURN_CHARS:
        raise AppError(422, "INTERVIEW_TURN_TOO_LONG", "발화가 너무 깁니다.")  # never cut
    if event.role == "agent" and not masked.text:
        raise _bad("text")  # a candidate's empty answer is a valid event, an empty line of the interviewer is not
    if not isinstance(event.method, str) or not _METHOD.match(event.method):
        raise _bad("method")
    kinds = _merge_masked_kinds(event.masked_kinds, masked.kinds)
    if event.role == "candidate":
        analysis, dropped = _clean_analysis(event.analysis, plan, index, masked.text)
    else:
        if event.analysis is not None:
            raise _bad("analysis")
        analysis, dropped = None, 0
    if closing:
        if event.coverage is not None:
            raise _bad("coverage")
        coverage = None
    else:
        if event.coverage is None:
            raise _bad_coverage("missing")
        coverage = _clean_coverage(event.coverage, plan, {LISTENING})
    return _Turn(event.seq, event.role, event.kind, index, masked.text, event.method, analysis, kinds, dropped, coverage)


def _merge_masked_kinds(given: object, found: Mapping[str, int]) -> dict[str, int]:
    """Counts only. The agent's counts, checked, plus what this backend's masking found; at most 10 kinds, 1000 each."""
    counts: dict[str, int] = {}
    if given is not None:
        if not isinstance(given, Mapping) or len(given) > _MAX_MASKED_KINDS:
            raise _bad("masked_kinds")
        for key, value in given.items():
            if not isinstance(key, str) or not _KIND_KEY.match(key) or not _is_int(value) or not 0 <= value <= _MAX_COUNT:
                raise _bad("masked_kinds")
            counts[key] = value
    for key, value in found.items():
        counts[key] = counts.get(key, 0) + value
    if len(counts) > _MAX_MASKED_KINDS:
        counts = dict(sorted(counts.items())[:_MAX_MASKED_KINDS])
    return {key: min(value, _MAX_COUNT) for key, value in sorted(counts.items())}


def _clean_analysis(analysis: object, plan: _Plan, index: int | None, answer_text: str) -> tuple[dict, int]:
    """The analysis as it is stored: valid in shape, never trusted for the coverage. Points must be this item's rubric points; a
    quote that is not in the masked answer is dropped (the same check the engine applies)."""
    if not isinstance(analysis, Mapping) or set(analysis) != {"answer_type", "points", "quotes", "method"}:
        raise _bad("analysis")
    if analysis["answer_type"] not in ANSWER_TYPES:
        raise _bad("analysis")
    method = analysis["method"]
    if not isinstance(method, str) or not _METHOD.match(method):
        raise _bad("analysis")
    points = analysis["points"]
    rubric = plan.rubric[index] if index is not None and index < len(plan.rubric) else frozenset()
    if not isinstance(points, Mapping) or len(points) > _MAX_POINTS:
        raise _bad("analysis")
    for pid, level in points.items():
        if not isinstance(pid, str) or pid not in rubric or level not in LEVELS:
            raise _bad("analysis")
    quotes = analysis["quotes"]
    if not isinstance(quotes, (list, tuple)) or len(quotes) > _MAX_QUOTES_IN or not all(isinstance(q, str) and len(q) <= _MAX_QUOTE_IN_CHARS for q in quotes):
        raise _bad("analysis")
    kept = verified_quotes(quotes, answer_text)
    return {"answer_type": analysis["answer_type"], "points": dict(sorted(points.items())), "quotes": list(kept), "method": method}, len(quotes) - len(kept)


# ── Validation of the coverage (pure, then against the stored state) ──


def normalize_end_reason(value: object) -> str:
    """One of END_REASONS. The part before a colon counts (`session_closed:x`); anything else becomes `agent_ended`."""
    if not isinstance(value, str):
        return DEFAULT_END_REASON
    head = value.strip().lower().split(":", 1)[0]
    return head if head in END_REASONS else DEFAULT_END_REASON


def _clean_coverage(snapshot: object, plan: _Plan, phases: set[str] | frozenset[str]) -> dict:
    """The snapshot as it is stored, or 422. Exactly the keys of `coverage_snapshot`, the topics of the stored plan, the engine's
    vocabularies, the points of each topic's rubric, within the size limit."""
    if not isinstance(snapshot, Mapping) or set(snapshot) != {"phase", "end_reason", "status", "levels"}:
        raise _bad_coverage("keys")
    phase = snapshot["phase"]
    if phase not in phases:
        raise _bad_coverage("phase")
    if phase == LISTENING:
        if snapshot["end_reason"] is not None:
            raise _bad_coverage("end_reason")
        reason = None
    else:
        reason = normalize_end_reason(snapshot["end_reason"])
    status, levels = snapshot["status"], snapshot["levels"]
    if not isinstance(status, Mapping) or not isinstance(levels, Mapping) or len(status) > _MAX_TOPICS or len(levels) > _MAX_TOPICS:
        raise _bad_coverage("shape")
    if set(status) != set(plan.topic_ids):
        raise _bad_coverage("topics")
    if any(value not in STATUSES for value in status.values()):
        raise _bad_coverage("status")
    clean_levels: dict[str, dict[str, str]] = {}
    for topic, points in levels.items():
        if topic not in plan.topic_ids or not isinstance(points, Mapping) or len(points) > _MAX_POINTS:
            raise _bad_coverage("levels")
        rubric = plan.rubric[plan.topic_ids.index(topic)]
        if any(pid not in rubric or level not in LEVELS for pid, level in points.items()):
            raise _bad_coverage("levels")
        clean_levels[topic] = dict(sorted(points.items()))
    clean = {
        "phase": phase,
        "end_reason": reason,
        "status": {topic: status[topic] for topic in plan.topic_ids},
        "levels": {topic: clean_levels[topic] for topic in plan.topic_ids if topic in clean_levels},
    }
    if len(json.dumps(clean, sort_keys=True, separators=(",", ":"))) > settings.INTERVIEW_COVERAGE_MAX_BYTES:
        raise _bad_coverage("size")
    return clean


def _check_coverage_state(previous: dict | None, new: dict, plan: _Plan, answered: set[int]) -> None:
    """The structural rules between the stored coverage and the new one. Nothing here reads a text or an analysis. 422 on a break."""
    before_status = previous["status"] if previous else {topic: "not_asked" for topic in plan.topic_ids}
    before_levels = previous["levels"] if previous else {}
    for topic in plan.topic_ids:
        old, current = before_status.get(topic, "not_asked"), new["status"][topic]
        if current not in STATUS_TRANSITIONS.get(old, frozenset()):
            raise _bad_coverage("status_transition")
        index = plan.topic_ids.index(topic)
        if (current in NEEDS_ANSWER or topic in new["levels"]) and index not in answered:
            raise _bad_coverage("status_without_answer")  # a status or a level that only an answer can give, and none is stored
    for topic, points in before_levels.items():
        for pid, level in points.items():
            now_level = new["levels"].get(topic, {}).get(pid)
            if now_level is None or LEVEL_RANK[now_level] < LEVEL_RANK[level]:
                raise _bad_coverage("level_regressed")  # the engine keeps the best level of every point so far


# ── Validation of the end event ──


def _clean_end(event: EndEvent, plan: _Plan, names: list[str]) -> _End:
    if not isinstance(event, EndEvent):
        raise _bad("event")
    coverage = _clean_coverage(event.coverage, plan, END_PHASES)
    closing = None
    if event.closing is not None:
        if coverage["phase"] != "ended":
            raise _bad("closing")  # an aborted interview has no closing line
        closing = _clean_turn(event.closing, plan, names, closing=True)
    status = InterviewStatus.COMPLETED if coverage["phase"] == "ended" else InterviewStatus.ABORTED
    return _End(status, coverage["end_reason"], coverage, closing)
