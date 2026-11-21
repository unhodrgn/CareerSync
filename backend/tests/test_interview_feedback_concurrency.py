"""Real parallel requests against the feedback service (M4 S3b): PostgreSQL only.

These need `TEST_DATABASE_URL=postgresql+psycopg://…` (a throwaway database: the fixture drops every table) and are SKIPPED without it.
The SQLite tests of the service (test_interview_feedback_service.py) step through the same races by running a second request inside the
model call, on one connection: that shows the logic and proves nothing about requests that run at the same time. Only these do, and
only when they run.

Threads have a session and a connection each. A model call is held open with events, so a test knows who has the lease and what the
others see; the assertions are on what must be true however the requests interleave: how many model calls and reservations were made,
that one report is stored, that a stale worker changed nothing."""
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, User
from app.services import ai_runtime
from app.services import interview_feedback_service as fb
from app.services import interview_service as svc

from .interview_feedback_fixtures import SpyLLM, askable_session, feedback_used, install, row
from .interview_fixtures import Clock, build_world
from .test_interview_ingest_concurrency import PG, parallel


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture(autouse=True)
def roomy(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 50)


def wait_for(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def attempt(call):
    """("ok", result) or ("refused", code, extra): a refusal is an answer here, anything else fails the test."""
    try:
        return "ok", call()
    except AppError as error:
        return "refused", error.code, error.extra


def ensure_in(session, uid, sid, clock):
    return fb.ensure(session, session.get(User, uid), sid, clock=clock)


class Worker:
    """A request in a thread of its own, with its own session; `finish` joins it and gives what it returned or raised."""

    def __init__(self, db, work, name):
        self.box: dict = {}
        factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)

        def run():
            session = factory()
            try:
                self.box["result"] = work(session)
            except BaseException as error:  # noqa: BLE001  (reported by the test)
                self.box["error"] = error
            finally:
                session.close()

        self.thread = threading.Thread(target=run, name=name)
        self.thread.start()

    def finish(self, timeout=30.0) -> dict:
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "a worker did not finish"
        return self.box


def by_thread(monkeypatch, **models):
    """Each thread gets its own model: `worker-a`, and the test's own thread as `main`."""
    monkeypatch.setattr(ai_runtime, "llm", lambda: models.get(threading.current_thread().name, models["main"]))


def hold(entered: threading.Event, go: threading.Event):
    """A model hook: say the call has started, then wait to be let go."""

    def hook(_llm):
        entered.set()
        assert go.wait(30), "the test never let the model go"

    return hook


# ── Many requests, one session ──


@PG
def test_pg_parallel_requests_on_one_session_make_one_model_call_and_the_rest_are_busy(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    finished: list[int] = []
    llm = SpyLLM(on_call=lambda _llm: wait_for(lambda: len(finished) >= 7))  # the holder waits until the other seven have been refused
    install(monkeypatch, llm)

    def work(session, index):
        out = attempt(lambda: ensure_in(session, uid, sid, clock))
        finished.append(index)
        return out

    results = parallel(db, 8, work)
    done = [r for r in results if r[0] == "ok"]
    busy = [r for r in results if r[0] == "refused"]
    assert len(done) == 1 and len(busy) == 7 and done[0][1].final and done[0][1].method == "llm:spy-llm"
    assert all(r[1] == fb.BUSY and 1 <= r[2]["retry_after_seconds"] <= settings.INTERVIEW_FEEDBACK_LEASE_SECONDS for r in busy)
    r = row(db, sid)
    assert (r.feedback_attempts, r.feedback_lease_token, r.feedback_method) == (1, None, "llm:spy-llm")
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1


@PG
def test_pg_a_refused_reservation_takes_nothing_even_when_many_requests_ask_at_once(db, world, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 0)
    sid, uid = askable_session(db, world, clock), world.user.id
    llm = SpyLLM()
    install(monkeypatch, llm)
    results = parallel(db, 6, lambda s, i: attempt(lambda: ensure_in(s, uid, sid, clock)))
    # a request that waited on the row lock of another one proceeds when that one rolls back: every one of them is refused by the quota
    assert all(r[0] == "ok" and r[1].limited and not r[1].final for r in results), results
    r = row(db, sid)
    assert (r.feedback, r.feedback_attempts, r.feedback_lease_token, r.feedback_lease_until) == (None, 0, None, None)
    assert llm.calls == [] and feedback_used(db, world, clock) == 0


@PG
def test_pg_in_rules_mode_parallel_requests_store_one_report_and_all_return_it(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    install(monkeypatch, None)
    results = parallel(db, 8, lambda s, i: attempt(lambda: ensure_in(s, uid, sid, clock)))
    assert all(r[0] == "ok" and r[1].final and r[1].method == "rules" for r in results), results
    # by content, not by repr: the request that stored the report returns its own dict, the others the one jsonb gave back, with its keys in jsonb's order
    assert all(r[1].data == results[0][1].data for r in results)
    r = row(db, sid)
    assert r.feedback == results[0][1].data and r.feedback_attempts == 0 and feedback_used(db, world, clock) == 0


@PG
def test_pg_a_session_whose_third_attempt_died_is_recovered_once_by_parallel_requests_without_a_model(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    llm = SpyLLM()
    install(monkeypatch, llm)
    db.execute(
        InterviewSession.__table__.update()
        .where(InterviewSession.id == sid)
        .values(feedback_attempts=3, feedback_lease_until=clock() - timedelta(seconds=1), feedback_lease_token="a" * 32)
    )
    db.commit()
    results = parallel(db, 6, lambda s, i: attempt(lambda: ensure_in(s, uid, sid, clock)))
    assert all(r[0] == "ok" and r[1].final and r[1].method == "rules" for r in results), results
    assert all(r[1].data == results[0][1].data for r in results)  # by content, as above
    assert llm.calls == [] and feedback_used(db, world, clock) == 0 and row(db, sid).feedback_lease_token is None


# ── Many sessions, one daily quota ──


@PG
def test_pg_two_sessions_of_one_seeker_share_one_reservation_and_the_loser_keeps_no_lease_or_attempt(db, world, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 1)
    first, second, uid = askable_session(db, world, clock), askable_session(db, world, clock), world.user.id
    llm = SpyLLM()
    install(monkeypatch, llm)
    sessions = (first, second)
    results = parallel(db, 2, lambda s, i: ensure_in(s, uid, sessions[i], clock))
    assert sorted((r.final, r.limited) for r in results) == [(False, True), (True, False)]
    loser = sessions[[r.limited for r in results].index(True)]
    r = row(db, loser)
    assert (r.feedback, r.feedback_attempts, r.feedback_lease_token, r.feedback_lease_until) == (None, 0, None, None)
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1


@PG
def test_pg_five_sessions_in_parallel_never_take_more_than_the_daily_limit(db, world, clock, monkeypatch):
    uid = world.user.id
    sessions = [askable_session(db, world, clock) for _ in range(5)]
    llm = SpyLLM(fail=True)  # a failed attempt consumes the reservation as well
    install(monkeypatch, llm)
    results = parallel(db, 5, lambda s, i: ensure_in(s, uid, sessions[i], clock))
    assert sorted(r.reason for r in results) == sorted([fb.REASON_MODEL_FAILED] * 3 + [fb.REASON_QUOTA] * 2)
    assert feedback_used(db, world, clock) == 3 and len(llm.calls) == 3
    for index, result in enumerate(results):
        r = row(db, sessions[index])
        assert (r.feedback, r.feedback_lease_token) == (None, None)
        assert r.feedback_attempts == (0 if result.limited else 1)


# ── Leases ──


@PG
def test_pg_worker_a_loses_its_lease_to_worker_b_and_finishes_after_b_stored(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    entered, go = threading.Event(), threading.Event()
    a_llm = SpyLLM(model="llm-a", on_call=hold(entered, go))
    b_llm = SpyLLM(model="llm-b")
    by_thread(monkeypatch, **{"worker-a": a_llm, "main": b_llm})
    a = Worker(db, lambda s: ensure_in(s, uid, sid, clock), "worker-a")
    assert entered.wait(30)
    clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)
    b_result = fb.ensure(db, db.get(User, uid), sid, clock=clock)
    assert (b_result.final, b_result.method, b_result.attempts_used) == (True, "llm:llm-b", 2)
    go.set()
    box = a.finish()
    assert "error" not in box
    assert (box["result"].final, box["result"].method) == (True, "llm:llm-b")  # A did not overwrite B and returned B's report
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_attempts, r.feedback_lease_token) == (b_result.data, "llm:llm-b", 2, None)
    assert feedback_used(db, world, clock) == 2


@PG
@pytest.mark.parametrize("fails, reason, method", [(True, fb.REASON_MODEL_FAILED, "rules"), (False, fb.REASON_LEASE_LOST, "llm:llm-a")])
def test_pg_worker_a_finishing_while_b_holds_the_lease_changes_nothing_and_cannot_release_it(db, world, clock, monkeypatch, fails, reason, method):
    """A's model fails (A then tries to release the lease) or succeeds (A then tries to store): either way B's lease, B's attempt and the
    empty report are left as they were, and A hands its own report back as provisional."""
    sid, uid = askable_session(db, world, clock), world.user.id
    entered, go = threading.Event(), threading.Event()
    install(monkeypatch, SpyLLM(model="llm-a", fail=fails, on_call=hold(entered, go)))
    a = Worker(db, lambda s: ensure_in(s, uid, sid, clock), "worker-a")
    assert entered.wait(30)
    clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)
    held = fb._claim(db, sid, uid, clock())  # B's T1: B holds the lease and is in its own model call
    assert isinstance(held, fb._Claimed) and held.attempt == 2
    lease = row(db, sid).feedback_lease_until
    go.set()
    box = a.finish()
    assert (box["result"].final, box["result"].reason, box["result"].method) == (False, reason, method)
    r = row(db, sid)
    assert (r.feedback_lease_token, r.feedback_lease_until, r.feedback_attempts, r.feedback) == (held.token, lease, 2, None)


@PG
def test_pg_a_session_deleted_during_generation_is_a_404_and_the_reservation_stays_spent(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    entered, go = threading.Event(), threading.Event()
    install(monkeypatch, SpyLLM(on_call=hold(entered, go)))
    a = Worker(db, lambda s: ensure_in(s, uid, sid, clock), "worker-a")
    assert entered.wait(30)
    svc.delete(db, db.get(User, uid), sid, clock=clock)
    go.set()
    box = a.finish()
    assert isinstance(box.get("error"), AppError) and (box["error"].status_code, box["error"].code) == (404, svc.NOT_FOUND)
    db.rollback()
    assert db.get(InterviewSession, sid) is None and feedback_used(db, world, clock) == 1


@PG
def test_pg_the_store_of_a_slow_worker_and_the_takeover_never_both_win(db, world, clock, monkeypatch):
    """Worker A's T3 races worker B's T1 on the same row, fifteen times: whichever the database lets in first, one report is stored,
    no reservation is lost or made twice, and no lease is left behind."""
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 200)
    uid = world.user.id
    for _ in range(15):
        sid = askable_session(db, world, clock)
        entered, go = threading.Event(), threading.Event()
        a_llm, b_llm = SpyLLM(model="llm-a", on_call=hold(entered, go)), SpyLLM(model="llm-b")
        by_thread(monkeypatch, **{"worker-a": a_llm, "main": b_llm})
        before = feedback_used(db, world, clock)
        a = Worker(db, lambda s: ensure_in(s, uid, sid, clock), "worker-a")
        assert entered.wait(30)
        clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)
        barrier = threading.Barrier(2)

        def release():
            barrier.wait(30)
            go.set()

        releaser = threading.Thread(target=release)
        releaser.start()
        barrier.wait(30)
        b = attempt(lambda: fb.ensure(db, db.get(User, uid), sid, clock=clock))
        releaser.join(30)
        box = a.finish()
        assert "error" not in box and b[0] == "ok", (box, b)
        r = row(db, sid)
        assert r.feedback is not None and r.feedback_method in ("llm:llm-a", "llm:llm-b") and r.feedback_lease_token is None
        calls = len(a_llm.calls) + len(b_llm.calls)
        assert r.feedback_attempts == calls and feedback_used(db, world, clock) - before == calls
        assert b[1].final and b[1].data == r.feedback  # B returns the stored report, whoever stored it
        clock.advance(1)


# ── No lock and no transaction during the model call ──


@PG
def test_pg_no_row_lock_and_no_transaction_is_held_during_the_model_call(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    seen = []

    def probe(_llm):
        with db.get_bind().connect() as other:  # NOWAIT: it fails at once if a lock is held on the row
            other.execute(text("SELECT id FROM interview_sessions WHERE id = :id FOR UPDATE NOWAIT"), {"id": sid})
            other.execute(text("SELECT seeker_id FROM interview_quota WHERE seeker_id = :uid FOR UPDATE NOWAIT"), {"uid": uid})
            other.rollback()
        seen.append(db.in_transaction())

    llm = SpyLLM(db, on_call=probe)
    install(monkeypatch, llm)
    assert fb.ensure(db, db.get(User, uid), sid, clock=clock).final
    assert seen == [False] and llm.in_transaction == [False]
