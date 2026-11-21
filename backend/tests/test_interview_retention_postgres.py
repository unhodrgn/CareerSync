"""Retention and deletion under real parallel requests and real transactions (M4 PostgreSQL QA, N8 purge side and N9): PostgreSQL only.

The SQLite tests of retention (test_interview_retention.py) show what the purge deletes, on one connection. Here, with a session and a
connection per request:

- a purge and the agent at the moment of expiry (the purge's clock says the session has expired, the agent's says it has not): the turns of the
  session go with it whichever comes first, none is left behind, the agent is told 404 or stored its turn or its end, and nothing raw reaches it;
- a session that expires while its feedback is being made: the purge removes it, the worker is told 404, and the reservation stays spent;
- several parallel runs of `maintenance` over a database that has not been maintained for a while (expired sessions with turns, one stale
  session of each status, a healthy one, quota rows of past days): no deadlock and no error, each stale session is settled by exactly one run
  and each past quota row deleted by exactly one, and what is left is exactly what should be left (and a last run finds nothing to do);
- the purge script, through sessions of its own and with its own clock: the counts it prints, the dry run that changes nothing;
- a transaction that fails between the two DELETE statements of a purge, or of a delete of one session, is rolled back whole: what the first
  statement removed is back, and no other connection ever saw it gone.

They need `TEST_DATABASE_URL` on PostgreSQL (see db_safety.py) and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77). The script is run through its `session_factory` seam, as the SQLite tests do: the engine of the application itself
(`SessionLocal`, built from `DATABASE_URL`) is deliberately not used by any test, so this file does not show that path.
"""
import importlib.util
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewQuota, InterviewSession, InterviewTurn, User
from app.models.interview import QuotaKind
from app.services import interview_feedback_service as fb
from app.services import interview_ingest_service as ingest
from app.services import interview_quota_service as quota_service
from app.services import interview_service as svc
from app.services.interview_time import as_utc

from .interview_feedback_fixtures import SpyLLM, askable_session, feedback_used, install
from .interview_fixtures import Clock, Ids, build_world, make_session, new_session
from .test_interview_feedback_concurrency import Worker, hold
from .test_interview_ingest_concurrency import PG, attempt, parallel
from .test_interview_ingest_end import end_ev, ready
from .test_interview_ingest_turns import ev

S, T, Q = InterviewSession.__table__, InterviewTurn.__table__, InterviewQuota.__table__
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "purge_interviews.py"
ROUNDS = 8
RUNS = 4


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def add(db, world, clock, status, *, turns=0, **overrides) -> int:
    """One session of the world's seeker with `turns` turns. Not expired unless `expires_at` says so."""
    now = clock()
    values = {"created_at": now, "expires_at": now + timedelta(days=29)} | overrides
    row = make_session(Ids(world.user.id, world.job_id, world.cv_profile_id), status=status, **values)
    db.add(row)
    db.flush()
    for seq in range(1, turns + 1):
        db.add(InterviewTurn(session_id=row.id, seq=seq, role="candidate", kind="answer", text=f"line {seq}"))
    db.commit()
    return row.id


def other_connection(db):
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)()


def counts(session) -> tuple[int, int]:
    """(sessions, turns), from a fresh look."""
    session.rollback()
    return session.scalar(select(func.count()).select_from(S)), session.scalar(select(func.count()).select_from(T))


# ── A purge and the agent at the moment of expiry ──


@PG
@pytest.mark.parametrize("racer", ["turn", "end"])
def test_postgres_a_purge_and_the_agent_at_the_moment_of_expiry_leave_no_orphan_and_no_raw_error(db, clock, racer):
    for i in range(ROUNDS):
        world = build_world(db, email=f"expiry{i}@interview.test")
        sid = new_session(db, world, clock)
        plan, seq = ready(db, sid, clock)
        expires = clock() + timedelta(seconds=100)
        db.execute(update(S).where(S.c.id == sid).values(expires_at=expires))
        db.commit()
        agent_clock, purge_clock = Clock(expires - timedelta(seconds=1)), Clock(expires)  # in time for the agent, expired for the purge
        event = ev(plan, seq, "agent", "follow_up") if racer == "turn" else end_ev(plan, seq)
        send = ingest.record_turn if racer == "turn" else ingest.record_end

        def work(session, index, sid=sid, event=event, send=send, agent_clock=agent_clock, purge_clock=purge_clock):
            if index == 0:
                return attempt(lambda: send(session, sid, event, clock=agent_clock))
            return ("purged", svc.purge_expired(session, now=purge_clock(), seeker_id=None, batch=50))

        agent, purged = parallel(db, 2, work)
        assert purged == ("purged", 1), (i, purged)
        db.rollback()
        db.expire_all()
        assert db.get(InterviewSession, sid) is None, i
        assert db.scalar(select(func.count()).select_from(T).where(T.c.session_id == sid)) == 0, i  # no turn outlived its session
        assert agent in {("stored" if racer == "turn" else "ended", ""), ("refused", "INTERVIEW_NOT_FOUND")}, (i, agent)


@PG
def test_postgres_a_session_that_expires_during_its_feedback_is_a_404_and_the_reservation_stays_spent(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    expires = clock() + timedelta(seconds=100)
    db.execute(update(S).where(S.c.id == sid).values(expires_at=expires))
    db.commit()
    early, late = Clock(expires - timedelta(seconds=1)), Clock(expires)
    entered, go = threading.Event(), threading.Event()
    install(monkeypatch, SpyLLM(on_call=hold(entered, go)))
    a = Worker(db, lambda s: fb.ensure(s, s.get(User, uid), sid, clock=early), "feedback-a")
    assert entered.wait(30)  # the lease, the attempt and the reservation are committed; the model is being asked
    assert svc.purge_expired(db, now=late(), seeker_id=None, batch=10) == 1
    go.set()
    box = a.finish()
    error = box.get("error")
    assert isinstance(error, AppError) and (error.status_code, error.code) == (404, svc.NOT_FOUND), box
    db.rollback()
    assert db.get(InterviewSession, sid) is None and counts(db) == (0, 0)
    assert feedback_used(db, world, early) == 1  # never given back


# ── Several maintenance runs at once ──


@dataclass
class Population:
    expired: list[int]  # sessions past their expiry, with two turns each
    stale: dict[str, int]  # one session of each status that went stale, with one turn each, not expired
    healthy_live: int  # a live session inside its budget, one turn
    healthy_done: int  # a completed one that has not expired, two turns
    live_deadline: object
    past_quota: int
    today_quota: int
    turns_left: int


def build_population(db, clock) -> Population:
    """What a database holds when nobody has run the maintenance for a while. One active session at most per seeker, so four seekers."""
    now, grace = clock(), timedelta(seconds=settings.INTERVIEW_END_GRACE_SECONDS)
    today = quota_service.kst_day(now)
    worlds = [build_world(db, email=f"population{i}@interview.test") for i in range(4)]
    expired = [
        add(db, world, clock, "completed" if n % 2 else "aborted", turns=2, created_at=now - timedelta(days=40), expires_at=now - timedelta(days=1))
        for world in worlds
        for n in range(6)
    ]
    stale = {
        "planning": add(db, worlds[0], clock, "planning", turns=1, active_until=now - timedelta(seconds=10)),
        "created": add(db, worlds[1], clock, "created", turns=1, active_until=now - timedelta(seconds=10)),
        "live": add(db, worlds[2], clock, "live", turns=1, active_until=now - grace - timedelta(seconds=60)),
    }
    live_deadline = now + timedelta(seconds=300)
    healthy_live = add(db, worlds[3], clock, "live", turns=1, active_until=live_deadline)
    healthy_done = add(db, worlds[3], clock, "completed", turns=2)
    for world in worlds:
        for day in (today - timedelta(days=1), today - timedelta(days=3), today):
            db.execute(insert(Q).values(seeker_id=world.user.id, kst_day=day, kind=QuotaKind.SESSION, used=1, quota_limit=3))
    db.commit()
    return Population(expired, stale, healthy_live, healthy_done, live_deadline, past_quota=8, today_quota=4, turns_left=3 * 1 + 1 + 2)


def assert_end_state(db, pop: Population, clock) -> None:
    """Exactly what should be left once the maintenance has run, however many times and however concurrently."""
    db.rollback()
    db.expire_all()
    rows = {r.id: r for r in db.scalars(select(InterviewSession))}
    assert set(rows) == {*pop.stale.values(), pop.healthy_live, pop.healthy_done}  # not one expired session is left, and nothing else is gone
    reasons = {"planning": "planning_lost", "created": "not_joined", "live": "stale_live"}
    for status, sid in pop.stale.items():
        stale = rows[sid]
        assert (stale.status, stale.end_reason, stale.active_until) == ("aborted", reasons[status], None), status
        assert stale.ended_at is not None, status
    live = rows[pop.healthy_live]
    assert (live.status, live.end_reason, as_utc(live.active_until)) == ("live", None, pop.live_deadline)  # a healthy session is not touched
    assert (rows[pop.healthy_done].status, rows[pop.healthy_done].end_reason) == ("completed", None)
    owners = list(db.scalars(select(T.c.session_id)))
    assert len(owners) == pop.turns_left and set(owners) <= set(rows)  # the turns of the purged sessions went with them: no orphan
    days = list(db.scalars(select(Q.c.kst_day)))
    assert days == [quota_service.kst_day(clock())] * pop.today_quota  # only the reservations of today are left
    assert all(isinstance(day, date) for day in days)


@PG
def test_postgres_parallel_maintenance_runs_leave_an_empty_end_state_without_a_deadlock(db, clock):
    pop = build_population(db, clock)
    reports = parallel(db, RUNS, lambda session, index: svc.maintenance(session, clock=clock, batch=3))
    assert sum(r.settled for r in reports) == 3  # each stale session is settled by exactly one run
    assert sum(r.purged_quota_rows for r in reports) == pop.past_quota  # and each past quota row deleted by exactly one
    assert sum(r.purged_sessions for r in reports) >= len(pop.expired)  # a run counts the sessions it selected, so two runs can count the same one
    assert all(not r.dry_run for r in reports)
    assert_end_state(db, pop, clock)
    again = svc.maintenance(db, clock=clock)
    assert (again.settled, again.purged_sessions, again.purged_quota_rows) == (0, 0, 0)  # nothing left to do


# ── The purge script ──


def load_script():
    spec = importlib.util.spec_from_file_location("purge_interviews_script_postgres", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def totals(db) -> tuple[int, int, int]:
    db.rollback()
    db.expire_all()
    return (*counts(db), db.scalar(select(func.count()).select_from(Q)))


@PG
def test_postgres_the_purge_script_dry_runs_then_settles_and_deletes_through_sessions_of_its_own(db, clock, capsys):
    pop = build_population(db, clock)
    script, factory = load_script(), sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    before = totals(db)
    assert script.main(["--dry-run"], session_factory=factory, clock=clock) == 0
    assert capsys.readouterr().out.strip() == (
        f"dry run, nothing changed: would_settle=3 would_purge_sessions={len(pop.expired)} would_purge_quota_rows={pop.past_quota}"
    )
    assert totals(db) == before  # a dry run changes nothing, in any table
    assert script.main(["--batch", "3"], session_factory=factory, clock=clock) == 0
    assert capsys.readouterr().out.strip() == f"settled=3 purged_sessions={len(pop.expired)} purged_quota_rows={pop.past_quota}"
    assert_end_state(db, pop, clock)
    assert script.main([], session_factory=factory, clock=clock) == 0  # safe to run again
    assert capsys.readouterr().out.strip() == "settled=0 purged_sessions=0 purged_quota_rows=0"


# ── A transaction that fails between two statements ──


class FailsOn:
    """Stands in for `sql_delete` in the service: the `call`-th statement it is asked to build fails the way a lost connection does."""

    def __init__(self, real, call):
        self.real, self.call, self.count = real, call, 0

    def __call__(self, *args, **kwargs):
        self.count += 1
        if self.count == self.call:
            raise OperationalError("DELETE", {}, Exception("connection lost"))
        return self.real(*args, **kwargs)


@PG
def test_postgres_a_purge_that_fails_between_its_two_deletes_is_rolled_back_whole(db, world, clock, monkeypatch):
    for _ in range(3):
        add(db, world, clock, "completed", turns=2, expires_at=clock() - timedelta(seconds=1))
    other = other_connection(db)
    assert counts(other) == (3, 6)
    with monkeypatch.context() as patched:
        patched.setattr(svc, "sql_delete", FailsOn(svc.sql_delete, 2))  # the turns are deleted, the sessions are not
        with pytest.raises(OperationalError):
            svc.purge_expired(db, now=clock(), seeker_id=None, batch=10)
        assert counts(other) == (3, 6)  # the first DELETE is in a transaction still open: nobody else sees the turns gone
        db.rollback()
    assert counts(other) == (3, 6) and counts(db) == (3, 6)  # and when it ends, they were never gone
    assert svc.purge_expired(db, now=clock(), seeker_id=None, batch=10) == 3  # the purge still works afterwards
    assert counts(other) == (0, 0)
    other.close()


@PG
def test_postgres_a_delete_that_fails_between_its_two_statements_is_rolled_back_whole(db, world, clock, monkeypatch):
    sid = add(db, world, clock, "completed", turns=3)
    other = other_connection(db)
    assert counts(other) == (1, 3)
    with monkeypatch.context() as patched:
        patched.setattr(svc, "sql_delete", FailsOn(svc.sql_delete, 2))  # the turns, then the session
        with pytest.raises(OperationalError):
            svc.delete(db, world.user, sid, clock=clock)
        assert counts(other) == (1, 3)
        db.rollback()
    assert counts(other) == (1, 3)  # the session and its turns are still there
    svc.delete(db, world.user, sid, clock=clock)
    assert counts(other) == (0, 0)
    other.close()
