"""A planner that outlived its lease, against the request that took its place (M4 PostgreSQL QA, N6): PostgreSQL only.

`create_session` keeps no transaction open while the planning model runs. T1 (the session as `planning`, with a lease, and the reservations)
is committed first; T3 (`planning -> created`, with the plan) is one compare-and-set that matches only a session that is still `planning`,
whose lease has not run out, that has not expired and that is the seeker's. The SQLite test of this steps through it on one connection by
running the next request inside the model call. These run it with real threads, each with a session and a connection of its own:

- A is held inside its planning model call; the next request B, whose clock says A's lease has run out (the clocks of the workers are their own),
  settles A as `planning_lost`, takes its own session and plans. When A is let go its T3 matches nothing: A is told 409
  `INTERVIEW_PLANNING_EXPIRED`, A's row stays aborted with no plan, B's session is untouched, and both reservations stay spent.
- The same two requests released together, several times: whichever of A's T3 and B's settlement the database lets in first, the seeker ends
  with exactly one of two pictures, never a mixture. Either A stored its plan and B was refused (409 `INTERVIEW_SESSION_ACTIVE`, taking
  nothing), or A was refused, its row is `planning_lost` without a plan, and B has the one created session.

They need `TEST_DATABASE_URL` on PostgreSQL (see db_safety.py) and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77)."""
import threading

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, User
from app.models.interview import QuotaKind
from app.services import interview_quota_service as quota
from app.services import interview_service as svc

from .interview_fixtures import CONSENT_VERSION, Clock, PlanLLM, build_world
from .test_interview_feedback_concurrency import Worker, by_thread, hold
from .test_interview_ingest_concurrency import PG

ROUNDS = 8


def create_in(session, uid, job_id, clock):
    return svc.create_session(session, session.get(User, uid), job_id, consent_transcript=True, consent_version=CONSENT_VERSION, clock=clock)


def sessions_of(db, uid):
    db.rollback()
    db.expire_all()
    return list(db.scalars(select(InterviewSession).where(InterviewSession.seeker_id == uid).order_by(InterviewSession.id)))


def used(db, uid, kind, clock):
    value = quota.used(db, uid, kind, now=clock())
    db.rollback()
    return value


def clocks():
    """A's clock is at the start; B's is past A's planning lease, as another server's would be."""
    a, b = Clock(), Clock()
    b.advance(settings.INTERVIEW_PLAN_LEASE_SECONDS + 10)
    return a, b


@PG
def test_postgres_a_planner_that_was_superseded_cannot_store_its_plan_and_the_newer_session_is_untouched(db, monkeypatch):
    world = build_world(db)
    uid, job_id = world.user.id, world.job_id
    clock_a, clock_b = clocks()
    entered, go = threading.Event(), threading.Event()
    a_llm, b_llm = PlanLLM(on_call=hold(entered, go)), PlanLLM()
    by_thread(monkeypatch, **{"planner-a": a_llm, "main": b_llm})
    a = Worker(db, lambda s: create_in(s, uid, job_id, clock_a), "planner-a")
    assert entered.wait(30)  # A has its session, its reservations and the lease, and is in the model call with no transaction open
    second = create_in(db, uid, job_id, clock_b)  # B: settles A's lost reservation, reserves, plans, stores
    assert second.view.status == "created"
    go.set()
    box = a.finish()
    error = box.get("error")
    assert isinstance(error, AppError) and (error.status_code, error.code) == (409, "INTERVIEW_PLANNING_EXPIRED"), box
    first, newer = sessions_of(db, uid)
    assert error.extra["session_id"] == first.id and newer.id == second.view.id
    assert (first.status, first.end_reason, first.plan, first.plan_sha256) == ("aborted", "planning_lost", None, None)  # nothing was brought back
    assert (newer.status, newer.plan is not None, newer.plan_sha256 is not None) == ("created", True, True)  # and nothing of B's was touched
    assert (len(a_llm.calls), len(b_llm.calls)) == (1, 1)
    assert used(db, uid, QuotaKind.SESSION, clock_b) == 2 and used(db, uid, QuotaKind.PLAN_MODEL, clock_b) == 2  # nothing is refunded


@PG
def test_postgres_a_stale_planner_and_the_next_request_released_together_leave_one_of_two_pictures(db, monkeypatch):
    seen = set()
    for i in range(ROUNDS):
        world = build_world(db, email=f"planner{i}@interview.test")
        uid, job_id = world.user.id, world.job_id
        clock_a, clock_b = clocks()
        entered, go = threading.Event(), threading.Event()
        a_llm, b_llm = PlanLLM(on_call=hold(entered, go)), PlanLLM()
        by_thread(monkeypatch, **{"planner-a": a_llm, "planner-b": b_llm, "main": PlanLLM()})
        barrier = threading.Barrier(2)

        def work_b(session, uid=uid, job_id=job_id, clock_b=clock_b):
            barrier.wait(30)
            return create_in(session, uid, job_id, clock_b)

        a = Worker(db, lambda s, uid=uid, job_id=job_id, clock_a=clock_a: create_in(s, uid, job_id, clock_a), "planner-a")
        assert entered.wait(30)
        b = Worker(db, work_b, "planner-b")
        barrier.wait(30)
        go.set()  # A is let go as B starts
        box_a, box_b = a.finish(), b.finish()
        rows = sessions_of(db, uid)
        if "result" in box_a:  # A's T3 came first
            refusal = box_b.get("error")
            assert isinstance(refusal, AppError) and (refusal.status_code, refusal.code) == (409, "INTERVIEW_SESSION_ACTIVE"), (i, box_a, box_b)
            assert refusal.extra["session_id"] == rows[0].id
            assert [(r.status, r.plan is not None) for r in rows] == [("created", True)], i
            assert used(db, uid, QuotaKind.SESSION, clock_b) == 1 and len(b_llm.calls) == 0, i  # B took nothing and never reached the model
            seen.add("A stored")
        else:  # B's settlement came first
            refusal = box_a.get("error")
            assert isinstance(refusal, AppError) and (refusal.status_code, refusal.code) == (409, "INTERVIEW_PLANNING_EXPIRED"), (i, box_a, box_b)
            assert "result" in box_b, (i, box_b)
            first, newer = rows
            assert (first.status, first.end_reason, first.plan, first.plan_sha256) == ("aborted", "planning_lost", None, None), i
            assert (newer.id, newer.status, newer.plan is not None) == (box_b["result"].view.id, "created", True), i
            assert used(db, uid, QuotaKind.SESSION, clock_b) == 2, i
            seen.add("B took over")
        assert len(a_llm.calls) == 1, i
        assert len([r for r in rows if r.status == "created"]) == 1, i  # never two
    assert seen <= {"A stored", "B took over"}  # (which of them happened, and how often, is the database's to say)
