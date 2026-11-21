"""More of the ingestion under real parallel requests (M4 PostgreSQL QA, N7 and the ingestion side of N8): PostgreSQL only.

N7, the order of a whole interview. A real `InterviewEngine` plays the interview, but nothing is posted while it plays (`Scribe`): its events
are then sent in waves of parallel requests, shuffled, with the refused ones resent in order, while another connection watches the stored
coverage. What must hold however the requests interleave: a gap names the exact next sequence number (and in parallel a number between the
stored end and the event), the stored turns are the engine's, in order, and the stored coverage is the engine's final one; and every
coverage that was ever visible followed the engine's own rules from the one before it: a topic's status only moved along the transitions
the engine makes, and no rubric level went down or disappeared.

N8, the deadline. The clocks of the workers are their own (the lease and the time budget are the application's clock), so a request whose clock
says "still in time" can meet a settlement whose clock says "too late". At the deadline, with the two requests released together, exactly one
of them wins and the rows say so: the agent's end event against `settle` and `maintenance`, a turn against them, and the feedback of a session
that went stale against them. A settlement that lands during a model call changes neither the lease nor the report that comes next.

They need `TEST_DATABASE_URL` on PostgreSQL (see db_safety.py) and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77)."""
import random
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from ai.interview import coverage_snapshot
from ai.interview.types import LEVEL_RANK
from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, User
from app.services import interview_feedback_service as fb
from app.services import interview_ingest_service as ingest
from app.services import interview_service as svc
from app.services.interview_time import as_utc

from .interview_feedback_fixtures import (
    ANSWER_TEXT,
    SpyLLM,
    agent_turn,
    candidate_turn,
    covered,
    feedback_used,
    hand_session,
    install,
    plan_item,
)
from .interview_feedback_fixtures import row as feedback_row
from .interview_fixtures import Agent, Clock, build_world, new_session, turn_rows
from .test_interview_feedback_concurrency import Worker, hold
from .test_interview_ingest_concurrency import PG, attempt, parallel, state
from .test_interview_ingest_end import end_ev, ready
from .test_interview_ingest_turns import ev, rec, refuse, started

S = InterviewSession.__table__
ROUNDS = 6
WAVE = 6


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


# ── N7: a gap names the next sequence number ──


@PG
def test_postgres_a_gap_names_the_exact_next_sequence_number_and_stores_nothing(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)  # seq 1 and 2 are stored
    for seq, expected in ((5, 3), (4, 3), (100, 3)):
        refuse(db, sid, ev(plan, seq, "agent", "follow_up"), clock, 409, "INTERVIEW_SEQ_GAP", expected_seq=expected)
        assert [t.seq for t in turn_rows(db, sid)] == [1, 2]  # a refused gap leaves nothing behind
    assert rec(db, sid, ev(plan, 3, "agent", "follow_up"), clock).outcome == "stored"
    refuse(db, sid, ev(plan, 5, "agent", "follow_up"), clock, 409, "INTERVIEW_SEQ_GAP", expected_seq=4)  # and the number moves with what is stored
    assert rec(db, sid, ev(plan, 4, "candidate", "answer"), clock).outcome == "stored"
    assert rec(db, sid, ev(plan, 5, "agent", "follow_up"), clock).outcome == "stored"
    assert [t.seq for t in turn_rows(db, sid)] == [1, 2, 3, 4, 5]


def classify(call):
    """("stored" | "duplicate", 0), ("gap", the expected sequence number) or ("refused:<code>", 0); anything else is not an answer."""
    try:
        return call().outcome, 0
    except AppError as error:
        if error.code == "INTERVIEW_SEQ_GAP":
            return "gap", error.extra["expected_seq"]
        return f"refused:{error.code}", 0


def turn(plan, seq):
    return ev(plan, seq, "agent", "follow_up") if seq % 2 else ev(plan, seq, "candidate", "answer")


@PG
def test_postgres_every_gap_refused_in_parallel_names_a_number_between_the_stored_end_and_the_event(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)
    events = [turn(plan, seq) for seq in range(3, 11)]
    results = parallel(db, len(events), lambda s, i: classify(lambda: ingest.record_turn(s, sid, events[i], clock=clock)))
    for event, (kind, expected) in zip(events, results, strict=True):
        assert kind in {"stored", "duplicate", "gap"}, (event.seq, kind)  # nothing else may happen to a valid event
        if kind == "gap":
            assert 3 <= expected < event.seq, (event.seq, expected)
    for event in events:  # the agent resends, in order
        classify(lambda e=event: ingest.record_turn(db, sid, e, clock=clock))
    db.rollback()
    _row, turns = state(db, sid)
    assert [t.seq for t in turns] == list(range(1, 11))


# ── N7: a whole interview, sent in waves ──


class Scribe(Agent):
    """The real engine, playing an interview, that posts nothing: `events` is what the agent would have sent, in order."""

    def _send(self, call, event):
        self.events.append(event)


def interview_script(db, sid: int) -> Scribe:
    scribe = Scribe(db, sid, Clock())  # its own clock: the backend's must stay at the start of the session
    scribe.start()
    for _ in range(40):
        if scribe.engine.state.phase.value in ("ended", "aborted"):
            break
        scribe.answer(ANSWER_TEXT)
    assert scribe.engine.state.phase.value == "ended"
    return scribe


def reachable() -> dict[str, set[str]]:
    out = {}
    for start in ingest.STATUS_TRANSITIONS:
        seen, todo = {start}, [start]
        while todo:
            for following in ingest.STATUS_TRANSITIONS[todo.pop()]:
                if following not in seen:
                    seen.add(following)
                    todo.append(following)
        out[start] = seen
    return out


def assert_followed_the_rules(before: dict, after: dict) -> None:
    """Two coverages seen one after the other: what happened between them is a path the engine can take."""
    steps = reachable()
    for topic, old in before["status"].items():
        assert after["status"][topic] in steps[old], (topic, old, after["status"][topic])
    for topic, points in before["levels"].items():
        for point_id, level in points.items():
            now = after["levels"].get(topic, {}).get(point_id)
            assert now is not None and LEVEL_RANK[now] >= LEVEL_RANK[level], (topic, point_id)


class Watcher:
    """Another connection that reads the stored coverage as fast as it can and keeps each different one it sees."""

    def __init__(self, engine, session_id):
        self.engine, self.session_id = engine, session_id
        self.snapshots: list[dict] = []
        self.error: BaseException | None = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, name="coverage-watcher")

    def run(self):
        try:
            with self.engine.connect() as connection:
                while not self.stopped.is_set():
                    value = connection.execute(select(S.c.coverage).where(S.c.id == self.session_id)).scalar()
                    connection.rollback()  # a new look each time, and never a transaction left open
                    if value is not None and (not self.snapshots or value != self.snapshots[-1]):
                        self.snapshots.append(value)
                    time.sleep(0.002)
        except BaseException as error:  # noqa: BLE001  (reported by the test)
            self.error = error

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stopped.set()
        self.thread.join(30)
        assert not self.thread.is_alive(), "the watcher did not stop"


def send_in_waves(db, sid, events, clock, seed=7):
    """Each wave goes out in parallel and shuffled; then the agent resends the whole wave in order. Gaps are checked as they come."""
    rng, outcomes = random.Random(seed), []
    for start in range(0, len(events), WAVE):
        wave = events[start : start + WAVE]
        shuffled = wave[:]
        rng.shuffle(shuffled)
        results = parallel(db, len(shuffled), lambda s, i: classify(lambda: ingest.record_turn(s, sid, shuffled[i], clock=clock)))
        for event, (kind, expected) in zip(shuffled, results, strict=True):
            assert kind in {"stored", "duplicate", "gap"}, (event.seq, kind)
            if kind == "gap":
                assert wave[0].seq <= expected < event.seq, (event.seq, expected)  # everything before this wave is stored
        outcomes += results
        for event in wave:
            classify(lambda e=event: ingest.record_turn(db, sid, e, clock=clock))
        db.rollback()
    return outcomes


@PG
def test_postgres_a_whole_interview_sent_in_parallel_waves_is_stored_as_the_engine_said_it(db, world, clock, sid):
    scribe = interview_script(db, sid)
    turns_out = [e for e in scribe.events if isinstance(e, ingest.TurnEvent)]
    end_event = scribe.events[-1]
    assert isinstance(end_event, ingest.EndEvent) and len(turns_out) > WAVE
    final_status = coverage_snapshot(scribe.engine.state)["status"]
    assert sum(1 for value in final_status.values() if value not in ("not_asked", "asked")) >= 2  # more than one topic really moved
    assert rec(db, sid, turns_out[0], clock).outcome == "stored"  # the first turn starts the session
    with Watcher(db.get_bind(), sid) as watcher:
        send_in_waves(db, sid, turns_out[1:], clock)
    assert watcher.error is None, watcher.error
    assert ingest.record_end(db, sid, end_event, clock=clock).outcome == "ended"
    stored = turn_rows(db, sid)
    assert [(t.seq, t.role, t.kind, t.item_index, t.text) for t in stored] == [
        (t.seq, t.role, t.kind, t.item_index, t.text) for t in scribe.engine.state.turns
    ]
    finished = feedback_row(db, sid)
    engine_final = coverage_snapshot(scribe.engine.state)
    assert (finished.status, finished.end_reason) == ("completed", ingest.normalize_end_reason(engine_final["end_reason"]))
    assert finished.coverage == engine_final  # the engine's final snapshot, whatever the order of arrival
    assert watcher.snapshots, "the watcher saw no coverage"
    for before, after in zip(watcher.snapshots, watcher.snapshots[1:], strict=False):
        assert_followed_the_rules(before, after)


# ── N8: the deadline ──


GRACE = timedelta(seconds=settings.INTERVIEW_END_GRACE_SECONDS)


def settle_now(session, when):
    """The two things that settle a stale session: the settlement itself, and the maintenance that the purge script runs."""
    return ("settled", svc.settle(session, None, when()))


def maintain_now(session, when):
    return ("settled", svc.maintenance(session, clock=when).settled)


SETTLERS = {"settle": settle_now, "maintenance": maintain_now}


def live_session(db, clock, name):
    world = build_world(db, email=f"{name}@interview.test")
    sid = new_session(db, world, clock)
    plan, seq = ready(db, sid, clock)
    return world, sid, plan, seq, as_utc(state(db, sid)[0].active_until)


@PG
@pytest.mark.parametrize("settler", SETTLERS)
def test_postgres_the_agents_end_at_the_last_second_of_the_grace_and_a_settlement_a_second_later_have_one_winner(db, clock, settler):
    for i in range(ROUNDS):
        _world, sid, plan, seq, deadline = live_session(db, clock, f"end{i}")
        agent, late = Clock(deadline + GRACE), Clock(deadline + GRACE + timedelta(seconds=1))  # in time for the agent, too late for the session
        event = end_ev(plan, seq)

        def work(session, index, sid=sid, event=event, agent=agent, late=late):
            if index == 0:
                return attempt(lambda: ingest.record_end(session, sid, event, clock=agent))
            return SETTLERS[settler](session, late)

        ended, settled = parallel(db, 2, work)
        row, turns = state(db, sid)
        closings = [t for t in turns if t.kind == "closing"]
        assert row.active_until is None, i
        if row.status == "completed":  # the end got in first: the settlement found nothing to settle
            assert ended == ("ended", "") and settled == ("settled", 0), (i, ended, settled)
            assert row.end_reason == "plan_exhausted" and [t.seq for t in turns] == [1, 2, 3] and len(closings) == 1
            assert row.coverage["phase"] == "ended"
        else:  # the settlement got in first: the end is refused, and not one line of it is stored
            assert (row.status, row.end_reason) == ("aborted", "stale_live"), (i, row.status, row.end_reason)
            assert ended == ("refused", "INTERVIEW_ALREADY_ENDED") and settled == ("settled", 1), (i, ended, settled)
            assert closings == [] and [t.seq for t in turns] == [1, 2] and row.coverage["phase"] == "listening"
        assert row.ended_at is not None


@PG
@pytest.mark.parametrize("settler", SETTLERS)
def test_postgres_a_turn_at_the_last_second_of_the_budget_and_a_settlement_after_the_grace_never_leave_a_turn_after_the_status(db, clock, settler):
    for i in range(ROUNDS):
        _world, sid, plan, seq, deadline = live_session(db, clock, f"turn{i}")
        agent, late = Clock(deadline), Clock(deadline + GRACE + timedelta(seconds=1))
        event = ev(plan, seq, "agent", "follow_up")

        def work(session, index, sid=sid, event=event, agent=agent, late=late):
            if index == 0:
                return attempt(lambda: ingest.record_turn(session, sid, event, clock=agent))
            return SETTLERS[settler](session, late)

        stored, settled = parallel(db, 2, work)
        row, turns = state(db, sid)
        assert (row.status, row.end_reason, row.active_until) == ("aborted", "stale_live", None), i  # the settlement always lands
        assert settled == ("settled", 1), (i, settled)
        if stored == ("stored", ""):  # the turn got in before the settlement
            assert [t.seq for t in turns] == [1, 2, 3], i
        else:  # the settlement came first
            assert stored == ("refused", "INTERVIEW_NOT_ACTIVE") and [t.seq for t in turns] == [1, 2], (i, stored)


# ── N8: a session that went stale, and its feedback ──


def stale_live_session(db, world, clock) -> int:
    """A live session whose time budget ends `INTERVIEW_MAX_SECONDS` after `clock()`, written by hand with a plan and one answer, so that
    a model is asked for its feedback once the clock is past the grace."""
    items = [plan_item(1, "Java"), plan_item(2, "Spring Boot"), plan_item(3, "협업", kind="behavioral")]
    quote = "Java 트랜잭션 처리를 직접 설계했습니다"
    turns = [agent_turn(1, 0, "Java를 실무에서 어떻게 사용했는지 설명해 주세요."), candidate_turn(2, 0, f"저는 {quote}. 그래서 장애가 줄었습니다.", quote)]
    coverage = covered(items, {"c1": "demonstrated"}, phase="listening", end_reason=None)
    sid = hand_session(db, world, clock, items, turns=turns, coverage=coverage, status="live", end_reason=None)
    db.execute(update(S).where(S.c.id == sid).values(ended_at=None, started_at=clock(), active_until=clock() + timedelta(seconds=settings.INTERVIEW_MAX_SECONDS)))
    db.commit()
    return sid


@PG
@pytest.mark.parametrize("settler", SETTLERS)
def test_postgres_a_settlement_during_the_model_call_of_a_feedback_changes_neither_the_lease_nor_the_report(db, world, clock, monkeypatch, settler):
    sid, uid = stale_live_session(db, world, clock), world.user.id
    deadline = as_utc(feedback_row(db, sid).active_until)
    late = Clock(deadline + GRACE + timedelta(seconds=5))  # stale for every reader: the feedback is of an aborted session
    entered, go = threading.Event(), threading.Event()
    llm = SpyLLM(on_call=hold(entered, go))
    install(monkeypatch, llm)
    a = Worker(db, lambda s: fb.ensure(s, s.get(User, uid), sid, clock=late), "feedback-a")
    assert entered.wait(30)
    assert SETTLERS[settler](db, late) == ("settled", 1)  # while the model is being asked
    during = feedback_row(db, sid)
    assert (during.status, during.end_reason) == ("aborted", "stale_live")
    assert during.feedback is None and during.feedback_lease_token is not None and during.feedback_attempts == 1  # the lease is still the worker's
    go.set()
    box = a.finish()
    assert "error" not in box and box["result"].final and box["result"].method == "llm:spy-llm", box
    after = feedback_row(db, sid)
    assert (after.status, after.end_reason, after.feedback_method, after.feedback_lease_token, after.feedback_attempts) == (
        "aborted", "stale_live", "llm:spy-llm", None, 1,
    )  # fmt: skip
    assert after.feedback == box["result"].data and len(llm.calls) == 1 and feedback_used(db, world, late) == 1


@PG
def test_postgres_a_feedback_and_a_settlement_released_together_leave_one_report_and_one_settled_session(db, clock, monkeypatch):
    llm = SpyLLM()
    install(monkeypatch, llm)
    for i in range(ROUNDS):
        world = build_world(db, email=f"stale{i}@interview.test")
        sid, uid = stale_live_session(db, world, clock), world.user.id
        late = Clock(as_utc(feedback_row(db, sid).active_until) + GRACE + timedelta(seconds=5))

        def work(session, index, sid=sid, uid=uid, late=late):
            if index == 0:
                return ("feedback", fb.ensure(session, session.get(User, uid), sid, clock=late))
            return settle_now(session, late)

        report, settled = parallel(db, 2, work)
        assert report[1].final and report[1].method == "llm:spy-llm" and settled == ("settled", 1), (i, settled)
        after = feedback_row(db, sid)
        assert (after.status, after.end_reason, after.feedback_method, after.feedback_lease_token, after.feedback_attempts) == (
            "aborted", "stale_live", "llm:spy-llm", None, 1,
        ), i  # fmt: skip
        assert after.feedback == report[1].data
    assert len(llm.calls) == ROUNDS


@PG
def test_postgres_the_scribe_posts_nothing_and_its_events_are_the_engines_own_in_order(db, world, clock, sid):
    """What N7 sends is the engine's, and the Scribe must not have sent any of it while it played."""
    scribe = interview_script(db, sid)
    assert turn_rows(db, sid) == []
    assert isinstance(scribe.events[-1], ingest.EndEvent) and all(isinstance(e, ingest.TurnEvent) for e in scribe.events[:-1])
    assert [e.seq for e in scribe.events[:-1]] == list(range(1, len(scribe.events)))  # one after the other, from 1
