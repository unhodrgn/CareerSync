"""Real parallel requests against the ingestion of a practice interview (M4 S3a): PostgreSQL only.

These need `TEST_DATABASE_URL=postgresql+psycopg://…` (a throwaway database: the fixture drops every table) and are SKIPPED without
it. The other S3a tests step through the same races on one SQLite connection by patching the point between two statements; that shows
the logic and proves nothing about requests that run at the same time. Only these do, and only when they run.

Each test releases its threads together with a barrier, every thread has its own session and connection, and the assertions are on what
is true however the requests interleave: how many are stored, that there is one closing line, that no turn follows the end."""
import os
import threading

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn
from app.services import interview_ingest_service as ingest
from app.services import interview_service as svc

from .interview_fixtures import Clock, build_world, new_session, turn_rows
from .test_interview_ingest_end import closing, end_ev, final, ready
from .test_interview_ingest_turns import ANSWER, cov, ev, plan_of, started

PG = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


def parallel(db, count, work):
    """Run `work(session, index)` in `count` threads with a session each, released together; the results, in order."""
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(count)
    results, errors = [None] * count, []

    def run(index):
        session = factory()
        try:
            barrier.wait(30)
            results[index] = work(session, index)
        except BaseException as error:  # noqa: BLE001  (reported by the test)
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads), "a thread did not finish"
    assert not errors, errors
    return results


def attempt(call):
    """(outcome, "") or ("refused", the AppError code): a refusal is an answer here, anything else fails the test."""
    try:
        return call().outcome, ""
    except AppError as error:
        return "refused", error.code


def state(db, sid):
    db.rollback()
    db.expire_all()
    return db.get(InterviewSession, sid), turn_rows(db, sid)


@PG
def test_pg_identical_turn_events_in_parallel_store_one_row_and_the_rest_are_duplicates(db, clock, sid):
    plan = started(db, sid, clock)
    event = ev(plan, 2, "candidate", "answer", coverage=cov(plan, {"c1": "partial"}))
    results = parallel(db, 8, lambda s, i: attempt(lambda: ingest.record_turn(s, sid, event, clock=clock)))
    assert sorted(results) == [("duplicate", "")] * 7 + [("stored", "")]
    row, turns = state(db, sid)
    assert [t.seq for t in turns] == [1, 2] and row.coverage["status"]["c1"] == "partial"


@PG
def test_pg_the_first_turn_in_parallel_starts_the_session_once(db, clock, sid):
    plan = plan_of(db, sid)
    event = ev(plan)
    results = parallel(db, 8, lambda s, i: attempt(lambda: ingest.record_turn(s, sid, event, clock=clock)))
    assert sorted(results) == [("duplicate", "")] * 7 + [("stored", "")]
    row, turns = state(db, sid)
    assert row.status == "live" and row.started_at is not None and [t.seq for t in turns] == [1]


@PG
def test_pg_different_events_for_one_sequence_number_leave_one_winner_and_never_two_rows(db, clock, sid):
    plan = started(db, sid, clock)
    texts = ["첫 번째 답변입니다.", "두 번째 답변입니다."]
    events = [ev(plan, 2, "candidate", "answer", text=texts[i % 2]) for i in range(6)]
    results = parallel(db, 6, lambda s, i: attempt(lambda: ingest.record_turn(s, sid, events[i], clock=clock)))
    row, turns = state(db, sid)
    assert [t.seq for t in turns] == [1, 2]
    winner = turns[1].text
    assert [r for r in results if r[0] == "stored"] == [("stored", "")]
    for index, result in enumerate(results):
        if result[0] != "stored":
            assert result == (("duplicate", "") if texts[index % 2] == winner else ("refused", "INTERVIEW_SEQ_CONFLICT"))
    assert row.coverage == cov(plan)  # the losers changed nothing


@PG
def test_pg_a_stream_sent_at_once_ends_contiguous_without_duplicates_once_the_gaps_are_resent(db, clock, sid):
    plan = started(db, sid, clock)
    events = [ev(plan, seq, "candidate" if seq % 2 == 0 else "agent", "answer" if seq % 2 == 0 else "follow_up") for seq in range(2, 14)]
    results = parallel(db, len(events), lambda s, i: attempt(lambda: ingest.record_turn(s, sid, events[i], clock=clock)))
    assert {r for r in results} <= {("stored", ""), ("duplicate", ""), ("refused", "INTERVIEW_SEQ_GAP")}  # nothing else may happen
    for _ in range(len(events)):  # the agent resends what was refused as a gap, in order
        for event in events:
            attempt(lambda e=event: ingest.record_turn(db, sid, e, clock=clock))
        db.rollback()
    row, turns = state(db, sid)
    assert [t.seq for t in turns] == list(range(1, 14))
    assert len({t.seq for t in turns}) == len(turns)


@PG
def test_pg_identical_end_events_in_parallel_end_the_session_once_with_one_closing_line(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    event = end_ev(plan, seq)
    results = parallel(db, 8, lambda s, i: attempt(lambda: ingest.record_end(s, sid, event, clock=clock)))
    assert sorted(results) == [("duplicate", "")] * 7 + [("ended", "")]
    row, turns = state(db, sid)
    assert row.status == "completed" and [t.kind for t in turns].count("closing") == 1 and len(turns) == 3


@PG
def test_pg_the_agents_end_races_the_seekers_end_and_exactly_one_wins(db, world, clock, sid):
    plan, seq = ready(db, sid, clock)
    event = end_ev(plan, seq)

    def work(session, index):
        if index < 3:
            return attempt(lambda: ingest.record_end(session, sid, event, clock=clock))
        view = svc.end(session, world.user, sid, clock=clock)
        return ("seeker", view.status)

    results = parallel(db, 6, work)
    row, turns = state(db, sid)
    closings = [t for t in turns if t.kind == "closing"]
    if row.status == "completed":  # the agent won: its end is stored once, with its closing line
        assert len(closings) == 1 and row.end_reason == "plan_exhausted"
        assert [r for r in results[:3] if r[0] == "ended"] == [("ended", "")]
    else:  # the seeker won: nothing of the agent's end is stored
        assert (row.status, row.end_reason, closings) == ("aborted", "seeker_ended", [])
        assert all(r in {("refused", "INTERVIEW_ALREADY_ENDED")} for r in results[:3])
    for r in results[3:]:
        assert r[0] == "seeker" and r[1] in {"completed", "aborted"}  # the seeker's End is idempotent either way


@PG
def test_pg_a_turn_racing_the_end_is_stored_before_it_or_refused_and_never_stored_after_it(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    turn = ev(plan, seq, "agent", "follow_up")
    finish = ingest.EndEvent(final(plan), None)

    def work(session, index):
        if index == 0:
            return attempt(lambda: ingest.record_turn(session, sid, turn, clock=clock))
        return attempt(lambda: ingest.record_end(session, sid, finish, clock=clock))

    outcome_turn, outcome_end = parallel(db, 2, work)
    row, turns = state(db, sid)
    assert outcome_end == ("ended", "") and row.status == "completed"
    if outcome_turn == ("stored", ""):
        assert [t.seq for t in turns] == [1, 2, 3]  # it got in before the end
    else:
        assert outcome_turn == ("refused", "INTERVIEW_NOT_ACTIVE") and [t.seq for t in turns] == [1, 2]  # the end got in first


@PG
def test_pg_turns_for_many_sessions_do_not_interfere(db, clock):
    worlds = [build_world(db, email=f"pg{i}@interview.test") for i in range(4)]
    clocks = [Clock() for _ in worlds]
    ids = [new_session(db, w, c) for w, c in zip(worlds, clocks, strict=True)]
    plans = [plan_of(db, i) for i in ids]

    def work(session, index):
        return attempt(lambda: ingest.record_turn(session, ids[index], ev(plans[index]), clock=clocks[index]))

    assert parallel(db, 4, work) == [("stored", "")] * 4
    db.rollback()
    assert db.scalar(select(func.count()).select_from(InterviewTurn)) == 4


@PG
def test_pg_a_turn_that_loses_the_unique_index_race_changes_no_coverage(db, clock, sid):
    """Two different turns race for seq 2 with different coverage; the loser's snapshot must not survive."""
    plan = started(db, sid, clock)
    first = ev(plan, 2, "candidate", "answer", text="가", coverage=cov(plan, {"c1": "partial"}))
    second = ev(plan, 2, "candidate", "answer", text="나", coverage=cov(plan, {"c1": "not_shown"}))
    results = parallel(db, 2, lambda s, i: attempt(lambda: ingest.record_turn(s, sid, [first, second][i], clock=clock)))
    row, turns = state(db, sid)
    winner = {"가": "partial", "나": "not_shown"}[turns[1].text]
    assert row.coverage["status"]["c1"] == winner and sorted(r[0] for r in results) == ["refused", "stored"]
