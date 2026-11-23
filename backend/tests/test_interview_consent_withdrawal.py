"""Withdrawing the AI consent ends the practice interviews in progress (M5 S3; docs/DECISIONS.md D17, D65 (5), D81; resolves Q39).

`consent_service.withdraw_ai` settles the seeker's planning, created and live sessions to `aborted` with the reason `consent_withdrawn`, in
the same transaction as the withdrawal. These tests show which sessions it claims and which it leaves alone, that it is one transaction,
that every reader then sees the same state (the seeker's detail, the agent's context and events, the feedback), and that a session that
was being planned when the consent was withdrawn is not sealed afterwards. The agent's side (the check before a model call, a call that
was already running) is in test_interview_agent_runner.py. Time is the test clock; the database is the SQLite fixture."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core import agent_auth
from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewQuota, InterviewSession, InterviewTurn, User
from app.schemas.auth import ConsentIn
from app.services import ai_runtime, consent_service
from app.services import interview_service as svc
from app.services.interview_time import as_utc

from .conftest import auth
from .interview_fixtures import Clock, Ids, PlanLLM, build_world, make_session, new_session
from .test_interview_ingest_turns import ev, plan_of
from .test_interview_internal_api import SECRET, turn_body

GRACE = settings.INTERVIEW_END_GRACE_SECONDS


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def reload(db, session_id) -> InterviewSession:
    db.expire_all()
    return db.get(InterviewSession, session_id)


def set_row(db, session_id, **values):
    db.query(InterviewSession).filter_by(id=session_id).update(values)
    db.commit()


def withdraw(db, world, clock):
    return consent_service.withdraw_ai(db, world.user, now=clock.now)


# ── Which sessions it ends ──


@pytest.mark.parametrize(
    "status, seconds_to_deadline",
    [("planning", 100), ("created", 200), ("live", 300), ("live", -10)],
    ids=["planning, lease valid", "created, within its join time", "live, within its budget", "live, in the end grace"],
)
def test_a_session_in_progress_is_ended_with_the_reason_consent_withdrawn(db, world, clock, status, seconds_to_deadline):
    sid = new_session(db, world, clock)
    set_row(db, sid, status=status, active_until=clock.now + timedelta(seconds=seconds_to_deadline), started_at=clock.now if status == "live" else None)
    quota_before = db.scalar(select(func.coalesce(func.sum(InterviewQuota.used), 0)))
    returned = withdraw(db, world, clock)
    row = reload(db, sid)
    assert (row.status, row.end_reason, row.active_until) == ("aborted", "consent_withdrawn", None)
    assert as_utc(row.ended_at) == clock.now
    assert returned.consent_ai_at is None and returned.consent_version == settings.CONSENT_VERSION  # as before: the version last agreed to stays
    assert db.scalar(select(func.coalesce(func.sum(InterviewQuota.used), 0))) == quota_before  # nothing refunded or taken


def test_the_active_session_slot_is_free_afterwards(db, world, clock):
    sid = new_session(db, world, clock)
    withdraw(db, world, clock)
    assert svc.history(db, world.user, clock=clock).active is None
    assert reload(db, sid).status == "aborted"


@pytest.mark.parametrize(
    "status, seconds_to_deadline, reason_read",
    [("created", -1, "not_joined"), ("live", -(GRACE + 1), "stale_live"), ("planning", -1, "planning_lost")],
    ids=["created past its join time", "live past its end grace", "planning past its lease"],
)
def test_a_session_past_its_deadline_is_not_claimed_and_keeps_its_own_reason(db, world, clock, status, seconds_to_deadline, reason_read):
    sid = new_session(db, world, clock)
    set_row(db, sid, status=status, active_until=clock.now + timedelta(seconds=seconds_to_deadline), started_at=clock.now if status == "live" else None)
    withdraw(db, world, clock)
    assert reload(db, sid).status == status  # the row is left for `settle`, as for the seeker's own End
    view = svc.detail(db, world.user, sid, clock=clock) if status != "planning" else None
    if view is not None:
        assert (view.status, view.end_reason) == ("aborted", reason_read)
    svc.settle(db, world.user.id, clock.now)
    assert (reload(db, sid).status, reload(db, sid).end_reason) == ("aborted", reason_read)


@pytest.mark.parametrize("status, reason", [("completed", "plan_exhausted"), ("aborted", "seeker_ended")])
def test_a_finished_session_is_left_as_it_is(db, world, clock, status, reason):
    sid = new_session(db, world, clock)
    ended = clock.now - timedelta(minutes=5)
    set_row(db, sid, status=status, end_reason=reason, ended_at=ended, active_until=None, started_at=ended)
    withdraw(db, world, clock)
    row = reload(db, sid)
    assert (row.status, row.end_reason, as_utc(row.ended_at)) == (status, reason, ended)


def test_another_seekers_session_is_never_touched(db, world, clock):
    other = build_world(db, email="other@interview.test")
    other_sid = new_session(db, other, clock)
    mine = new_session(db, world, clock)
    withdraw(db, world, clock)
    assert reload(db, mine).status == "aborted"
    assert (reload(db, other_sid).status, reload(db, other_sid).end_reason) == ("created", None)
    assert db.get(User, other.user.id).consent_ai_at is not None


def test_a_seeker_with_no_sessions_withdraws_as_before(db, world, clock):
    assert withdraw(db, world, clock).consent_ai_at is None
    assert db.scalar(select(func.count()).select_from(InterviewSession)) == 0


def test_withdrawing_twice_is_harmless(db, world, clock):
    sid = new_session(db, world, clock)
    withdraw(db, world, clock)
    first = reload(db, sid)
    ended_at = first.ended_at
    withdraw(db, world, clock)
    again = reload(db, sid)
    assert (again.status, again.end_reason, again.ended_at) == ("aborted", "consent_withdrawn", ended_at)


def test_only_seekers_withdraw_and_nothing_is_changed_for_a_company(db, world, clock):
    sid = new_session(db, world, clock)
    company = build_world(db, email="hr@interview.test", role="company")
    with pytest.raises(AppError) as refused:
        consent_service.withdraw_ai(db, company.user, now=clock.now)
    assert refused.value.status_code == 403
    assert reload(db, sid).status == "created"


# ── One transaction ──


def test_the_withdrawal_and_the_ending_of_the_sessions_are_one_transaction(db, world, clock, monkeypatch):
    sid = new_session(db, world, clock)

    def fails(_db, _seeker_id, _now):
        raise RuntimeError("the update failed")

    monkeypatch.setattr(consent_service, "abort_for_consent_withdrawal", fails)
    with pytest.raises(RuntimeError):
        withdraw(db, world, clock)
    db.rollback()  # what the request's session does when the request fails
    db.expire_all()
    assert db.get(User, world.user.id).consent_ai_at is not None, "the consent was committed before the sessions were ended"
    assert reload(db, sid).status == "created"


# ── Every reader sees the same state ──


def test_after_the_withdrawal_the_seeker_the_agent_and_the_feedback_all_see_an_ended_session(client, db, world, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", SECRET)
    now = Clock(datetime.now(UTC))  # the route reads the real clock
    sid = new_session(db, world, now)
    seeker, room = auth(world.user), {agent_auth.SECRET_HEADER: SECRET, agent_auth.ROOM_HEADER: agent_auth.room_name(sid, SECRET)}
    before = client.delete("/api/users/me/consent/ai", headers=seeker)
    assert before.status_code == 200 and (before.json()["consent_required"], before.json()["consent_version"]) == (True, settings.CONSENT_VERSION)
    detail = client.get(f"/api/interview-sessions/{sid}", headers=seeker).json()
    assert (detail["status"], detail["end_reason"], detail["joinable"], detail["accepting_turns"]) == ("aborted", "consent_withdrawn", False, False)
    context = client.get(f"/api/internal/interview-sessions/{sid}/context", headers=room).json()
    assert (context["status"], context["end_reason"], context["ai_consent"]) == ("aborted", "consent_withdrawn", False)
    turn = turn_body(ev(plan_of(db, sid)))  # a valid first question: it is the lifecycle that refuses it
    refused = client.post(f"/api/internal/interview-sessions/{sid}/events", json=turn, headers=room)
    assert refused.status_code == 409 and refused.json()["code"] == "INTERVIEW_NOT_ACTIVE"
    assert db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
    feedback = client.post(f"/api/interview-sessions/{sid}/feedback", headers=seeker)
    assert feedback.status_code == 409 and feedback.json()["code"] == "AI_CONSENT_REQUIRED"  # a new report needs the consent (D64)
    create = client.post(f"/api/jobs/{world.job_id}/interview-sessions", json={"consent_transcript": True, "consent_version": settings.INTERVIEW_CONSENT_VERSION}, headers=seeker)
    assert (create.status_code, create.json()["code"]) == (409, "AI_CONSENT_REQUIRED")
    assert client.get(f"/api/interview-sessions/{sid}", headers=seeker).status_code == 200  # reading what is stored stays possible (D67 (8))


# ── A session that is being planned ──


def create(db, world, clock):
    return svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version=settings.INTERVIEW_CONSENT_VERSION, clock=clock)


def test_a_session_planned_while_the_consent_is_withdrawn_is_not_sealed_and_the_error_is_the_consent_error(db, world, clock, monkeypatch):
    def withdraw_during_the_call(_llm):
        consent_service.withdraw_ai(db, world.user, now=clock.now)

    monkeypatch.setattr(ai_runtime, "llm", lambda: PlanLLM(db, on_call=withdraw_during_the_call))
    with pytest.raises(AppError) as refused:
        create(db, world, clock)
    expected = svc.consent_required_error()  # the error every interview refusal by consent uses, the join route's too (M5 S4)
    assert (refused.value.status_code, refused.value.code, refused.value.message) == (409, "AI_CONSENT_REQUIRED", expected.message)
    assert refused.value.code != "INTERVIEW_PLANNING_EXPIRED"
    (row,) = db.query(InterviewSession).all()
    db.refresh(row)
    assert (row.status, row.end_reason, row.plan) == ("aborted", "consent_withdrawn", None)  # the plan the model made is not stored
    assert svc.history(db, db.get(User, world.user.id), clock=clock).active is None


def test_a_seeker_who_consented_again_before_the_error_is_told_to_start_again(db, world, clock, monkeypatch):
    def withdraw_and_consent_again(_llm):
        consent_service.withdraw_ai(db, world.user, now=clock.now)
        consent_service.consent(db, world.user, ConsentIn(version=settings.CONSENT_VERSION, consent_privacy=True, consent_ai=True))

    monkeypatch.setattr(ai_runtime, "llm", lambda: PlanLLM(db, on_call=withdraw_and_consent_again))
    with pytest.raises(AppError) as refused:
        create(db, world, clock)
    assert (refused.value.status_code, refused.value.code) == (409, "INTERVIEW_PLANNING_EXPIRED")
    (row,) = db.query(InterviewSession).all()
    db.refresh(row)
    assert (row.status, row.end_reason, row.plan) == ("aborted", "consent_withdrawn", None)


def test_the_consent_error_has_the_code_of_the_other_ai_features():
    error = svc.consent_required_error()
    assert (error.status_code, error.code) == (409, "AI_CONSENT_REQUIRED")


def test_the_function_counts_what_it_ends_and_leaves_the_commit_to_the_caller(db, world, clock):
    sid = new_session(db, world, clock)
    ids = Ids(world.user.id, world.job_id, world.cv_profile_id)
    db.add(make_session(ids, status="aborted", end_reason="seeker_ended", ended_at=clock.now, active_until=None))
    db.commit()
    assert svc.abort_for_consent_withdrawal(db, world.user.id, clock.now) == 1
    db.rollback()
    assert reload(db, sid).status == "created"  # not committed by the function itself: that is the caller's transaction
