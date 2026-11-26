"""Real parallel `create_session` calls of one seeker (M4 S3c): PostgreSQL only.

These need `TEST_DATABASE_URL=postgresql+psycopg://…/<name>_pgtest` on this machine (a throwaway database: the fixture drops every table)
and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77); no other test covers the partial unique index `uq_interview_sessions_active`
under real concurrency, and the SQLite fixture cannot (it is one connection).

What must hold however the requests interleave: one request wins and the others are told there is an active session (409
`INTERVIEW_SESSION_ACTIVE`, with the winner's id), exactly one session exists, the daily session quota is taken exactly once, and what a
losing request had reserved is rolled back with it (a loser takes nothing, and never reaches the planning model)."""
import time

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewQuota, InterviewSession, User
from app.models.interview import QuotaKind
from app.services import ai_runtime
from app.services import interview_quota_service as quota
from app.services import interview_service as svc

from .interview_fixtures import Clock, PlanLLM, build_world
from .test_interview_ingest_concurrency import PG, parallel

THREADS = 8


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def wait_for(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def create_in(session, uid, job_id, clock):
    """("ok", the CreatedSession) or ("refused", status, code, extra): a refusal is an answer here, anything else fails the test."""
    try:
        user = session.get(User, uid)
        return "ok", svc.create_session(session, user, job_id, consent_transcript=True, consent_version="2026-11-26", clock=clock)
    except AppError as error:
        return "refused", error.status_code, error.code, error.extra


def used(db, uid, kind, clock):
    value = quota.used(db, uid, kind, now=clock())
    db.rollback()
    return value


def sessions_of(db, uid):
    db.rollback()
    db.expire_all()
    return db.query(InterviewSession).filter_by(seeker_id=uid).all()


@PG
def test_pg_simultaneous_creates_of_one_seeker_have_one_winner_and_the_losers_take_nothing(db, world, clock, monkeypatch):
    uid, job_id = world.user.id, world.job_id
    finished: list[int] = []
    # The winner is held in its planning model call until every other request has been answered, so each loser meets a session that is
    # still `planning`, and the planning model (reserved by the winner only) is called once
    llm = PlanLLM(on_call=lambda _llm: wait_for(lambda: len(finished) >= THREADS - 1))
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)

    def work(session, index):
        out = create_in(session, uid, job_id, clock)
        finished.append(index)
        return out

    results = parallel(db, THREADS, work)
    winners = [r for r in results if r[0] == "ok"]
    losers = [r for r in results if r[0] == "refused"]
    assert len(winners) == 1 and len(losers) == THREADS - 1, results
    created = winners[0][1]
    assert created.view.status == "created" and created.limited is False
    for _kind, http, code, extra in losers:
        assert (http, code) == (409, "INTERVIEW_SESSION_ACTIVE")
        assert extra["session_id"] == created.view.id and extra["status"] == "planning"
    rows = sessions_of(db, uid)
    assert [(r.id, r.status) for r in rows] == [(created.view.id, "created")]  # one session, and no row of a loser
    assert len(llm.calls) == 1  # no loser reached the planning model
    # The session quota is taken once and so is the planning-model quota (the winner's); nothing of a loser was kept
    assert used(db, uid, QuotaKind.SESSION, clock) == 1 and used(db, uid, QuotaKind.PLAN_MODEL, clock) == 1
    assert used(db, uid, QuotaKind.FEEDBACK_MODEL, clock) == 0


@PG
def test_pg_simultaneous_creates_in_rules_mode_take_the_session_quota_exactly_once(db, world, clock, monkeypatch):
    uid, job_id = world.user.id, world.job_id
    monkeypatch.setattr(ai_runtime, "llm", lambda: None)  # no model: nothing holds the winner, so the interleaving is the database's
    results = parallel(db, THREADS, lambda session, index: create_in(session, uid, job_id, clock))
    winners = [r for r in results if r[0] == "ok"]
    losers = [r for r in results if r[0] == "refused"]
    assert len(winners) == 1 and len(losers) == THREADS - 1, results
    assert all((http, code) == (409, "INTERVIEW_SESSION_ACTIVE") and extra["session_id"] == winners[0][1].view.id for _k, http, code, extra in losers)
    assert [r.id for r in sessions_of(db, uid)] == [winners[0][1].view.id]
    assert used(db, uid, QuotaKind.SESSION, clock) == 1 and used(db, uid, QuotaKind.PLAN_MODEL, clock) == 0


@PG
def test_pg_when_the_daily_session_quota_is_gone_every_simultaneous_create_is_refused_and_leaves_no_row(db, world, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 0)
    monkeypatch.setattr(ai_runtime, "llm", lambda: None)
    uid, job_id = world.user.id, world.job_id
    results = parallel(db, THREADS, lambda session, index: create_in(session, uid, job_id, clock))
    # A request that waited on the unique index of another one proceeds when that one is rolled back, and is refused by the quota in turn
    assert all(r[0] == "refused" and (r[1], r[2]) == (429, "INTERVIEW_DAILY_LIMIT") for r in results), results
    assert sessions_of(db, uid) == []  # the session of each refused request was rolled back with its reservation
    db.rollback()
    assert db.query(InterviewQuota).filter_by(seeker_id=uid).count() == 0  # not even the ledger row of the day was kept
