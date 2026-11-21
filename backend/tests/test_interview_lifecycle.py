"""The session lifecycle (M4 S2): detail, history, end, delete and settlement.

R9: a GET shows the derived status and never changes a row; create, end and the purge script settle. Time is UTC, and the
stale thresholds of the overlay and of the settlement are the same. SQLite returns naive datetimes, PostgreSQL aware ones; both are
exercised (the read from the database is naive on SQLite, an unsaved row is aware)."""
from datetime import UTC, timedelta

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.models.interview import InterviewStatus as S, QuotaKind
from app.services import interview_quota_service as quota, interview_service as svc
from app.services.interview_time import as_utc

from .interview_fixtures import Clock, Ids, build_world, make_session

TABLE = InterviewSession.__table__


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def ids_of(world) -> Ids:
    return Ids(world.user.id, world.job_id, world.cv_profile_id)


def add(db, world, clock, status=S.CREATED, *, deadline=None, expires_in=30 * 86400, **overrides):
    """A session row as the lifecycle would have left it, `deadline` seconds after the clock's now."""
    now = clock()
    values = {"status": status, "created_at": now, "expires_at": now + timedelta(seconds=expires_in)}
    if deadline is not None:
        values["active_until"] = now + timedelta(seconds=deadline)
    if status == S.LIVE:
        values.setdefault("started_at", now)
    values.update(overrides)
    row = make_session(ids_of(world), **values)
    db.add(row)
    db.commit()
    return row.id


def physical(db, session_id):
    """What the row itself says (not an ORM object, so nothing cached)."""
    return tuple(db.execute(select(TABLE.c.status, TABLE.c.end_reason, TABLE.c.ended_at, TABLE.c.active_until, TABLE.c.expires_at).where(TABLE.c.id == session_id)).one())


def quota_rows(db):
    return sorted(tuple(r) for r in db.execute(select(InterviewQuota.seeker_id, InterviewQuota.kst_day, InterviewQuota.kind, InterviewQuota.used, InterviewQuota.quota_limit)))


def refuse(call, status, code):
    with pytest.raises(AppError) as error:
        call()
    assert (error.value.status_code, error.value.code) == (status, code)


# ── A GET shows the derived status and does not settle ──

# (status, deadline offset, time offset) -> (status shown, reason, joinable, accepting_turns, end_grace_open)
OVERLAY = [
    (S.PLANNING, 120, 100, (S.PLANNING, None, False, False, False)),
    (S.PLANNING, 120, 121, (S.ABORTED, "planning_lost", False, False, False)),
    (S.CREATED, 300, 300, (S.CREATED, None, True, True, False)),
    (S.CREATED, 300, 301, (S.ABORTED, "not_joined", False, False, False)),
    (S.LIVE, 600, 600, (S.LIVE, None, False, True, False)),
    (S.LIVE, 600, 601, (S.LIVE, None, False, False, True)),
    (S.LIVE, 600, 630, (S.LIVE, None, False, False, True)),
    (S.LIVE, 600, 631, (S.ABORTED, "stale_live", False, False, False)),
]


@pytest.mark.parametrize("status, deadline, later, expected", OVERLAY)
def test_a_read_shows_the_derived_status_and_leaves_the_row_alone(db, world, clock, status, deadline, later, expected):
    session_id = add(db, world, clock, status, deadline=deadline)
    clock.advance(later)
    before = physical(db, session_id)
    view = svc.detail(db, world.user, session_id, clock=clock)
    page = svc.history(db, world.user, clock=clock)
    assert (view.status, view.end_reason, view.joinable, view.accepting_turns, view.end_grace_open) == expected
    assert (page.items[0].status, page.items[0].end_reason, page.items[0].joinable) == (expected[0], expected[1], expected[2])
    assert physical(db, session_id) == before  # no lifecycle update on a GET
    if view.status == S.ABORTED:
        assert view.active_until is None and view.ended_at == as_utc(before[3]) and page.items[0].ended_at == view.ended_at


def test_the_naive_values_sqlite_returns_and_the_aware_ones_give_the_same_answer(db, world, clock):
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    clock.advance(301)
    db.expire_all()
    loaded, title = svc._load_own(db, world.user.id, session_id, clock())
    if db.get_bind().dialect.name == "sqlite":
        assert loaded.active_until.tzinfo is None  # the case this test is for
    from_database = svc._summary(loaded, title, clock())
    unsaved = make_session(ids_of(world), status=S.CREATED, active_until=clock() - timedelta(seconds=1), expires_at=clock() + timedelta(days=1), created_at=clock())
    unsaved.id = 99
    assert unsaved.active_until.tzinfo is not None  # aware, as PostgreSQL returns it
    from_aware = svc._summary(unsaved, title, clock())
    for summary in (from_database, from_aware):
        assert (summary.status, summary.end_reason, summary.joinable) == ("aborted", "not_joined", False)
        assert summary.expires_at.tzinfo is not None and summary.created_at.tzinfo is not None


def test_a_detail_has_the_topics_with_their_statuses_and_the_masked_turns(db, world, clock):
    session_id = svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-16", clock=clock).view.id
    db.add(InterviewTurn(session_id=session_id, seq=1, role="agent", kind="question", text="자기소개를 해 주세요."))
    db.add(InterviewTurn(session_id=session_id, seq=2, role="candidate", kind="answer", text="저는 [이름]입니다."))
    db.commit()
    row = db.get(InterviewSession, session_id)
    row.coverage = {"phase": "listening", "status": {"c1": "partial", "c2": "asked"}, "levels": {}}
    db.commit()
    view = svc.detail(db, world.user, session_id, clock=clock)
    assert [(t.seq, t.role, t.text) for t in view.turns] == [(1, "agent", "자기소개를 해 주세요."), (2, "candidate", "저는 [이름]입니다.")]
    assert {t.topic_id: t.status for t in view.topics} == {"c1": "partial", "c2": "asked", "c3": "not_asked", "behavioral": "not_asked"}
    assert view.job_title == "Backend Engineer" and view.max_seconds == 600


def test_a_stored_plan_that_cannot_be_read_shows_no_topics(db, world, clock):
    session_id = add(db, world, clock, S.CREATED, deadline=300, plan={"items": "not a list"})
    assert svc.detail(db, world.user, session_id, clock=clock).topics == ()
    assert svc.detail(db, world.user, add(db, world, clock, S.COMPLETED, plan=None), clock=clock).topics == ()


# ── Who can read ──


@pytest.mark.parametrize("call", ["detail", "end", "delete"])
def test_another_seekers_session_is_not_found(db, world, clock, call):
    mine = add(db, world, clock, S.CREATED, deadline=300)
    other = build_world(db, email="other@interview.test")
    refuse(lambda: getattr(svc, call)(db, other.user, mine, clock=clock), 404, "INTERVIEW_NOT_FOUND")
    assert physical(db, mine)[0] == S.CREATED  # and nothing happened to it
    assert svc.history(db, other.user, clock=clock).items == ()


def test_a_company_user_is_refused_by_every_service_before_any_statement(db, world, clock):
    from .test_interview_create import capture

    company = build_world(db, email="hr@interview.test", role="company")
    mine = add(db, world, clock, S.CREATED, deadline=300)
    calls = {
        "create": lambda: svc.create_session(db, company.user, company.job_id, consent_transcript=True, consent_version="2026-11-16", clock=clock),
        "detail": lambda: svc.detail(db, company.user, mine, clock=clock),
        "history": lambda: svc.history(db, company.user, clock=clock),
        "history_for_a_job": lambda: svc.history(db, company.user, job_id=world.job_id, clock=clock),
        "end": lambda: svc.end(db, company.user, mine, clock=clock),
        "delete": lambda: svc.delete(db, company.user, mine, clock=clock),
    }
    for name, call in calls.items():
        with capture(db) as log:
            refuse(call, 403, "SEEKER_ONLY")
        assert log == [], name
    assert physical(db, mine)[0] == S.CREATED


# ── Expiry hides a session from every path ──


def test_an_expired_session_is_hidden_from_every_read_and_action(db, world, clock):
    expired = add(db, world, clock, S.COMPLETED, expires_in=-1)
    live = add(db, world, clock, S.ABORTED, expires_in=86400)
    refuse(lambda: svc.detail(db, world.user, expired, clock=clock), 404, "INTERVIEW_NOT_FOUND")
    refuse(lambda: svc.end(db, world.user, expired, clock=clock), 404, "INTERVIEW_NOT_FOUND")
    refuse(lambda: svc.delete(db, world.user, expired, clock=clock), 404, "INTERVIEW_NOT_FOUND")
    assert [i.id for i in svc.history(db, world.user, clock=clock).items] == [live]
    assert [i.id for i in svc.history(db, world.user, job_id=world.job_id, clock=clock).items] == [live]


def test_a_session_expires_exactly_at_expires_at(db, world, clock):
    session_id = add(db, world, clock, S.COMPLETED, expires_in=100)
    clock.advance(99.999)
    assert svc.detail(db, world.user, session_id, clock=clock).id == session_id
    clock.advance(0.001)
    refuse(lambda: svc.detail(db, world.user, session_id, clock=clock), 404, "INTERVIEW_NOT_FOUND")


def test_expires_at_is_never_extended(db, world, clock):
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    stored = physical(db, session_id)[4]
    clock.advance(10)
    svc.detail(db, world.user, session_id, clock=clock)
    svc.end(db, world.user, session_id, clock=clock)
    svc.settle(db, None, clock())
    assert physical(db, session_id)[4] == stored


# ── History ──


def test_the_history_is_newest_first_with_a_cursor_and_a_job_filter(db, world, clock):
    first = add(db, world, clock, S.COMPLETED)
    second = add(db, world, clock, S.ABORTED)
    third = add(db, world, clock, S.COMPLETED)
    other_job = build_world(db, email="two@interview.test")  # another seeker and job: not in this history
    add(db, other_job, clock, S.COMPLETED)
    page = svc.history(db, world.user, clock=clock)
    assert [i.id for i in page.items] == [third, second, first] and page.next_before_id is None
    assert page.items[0].job_title == "Backend Engineer" and page.items[0].feedback_status == "none"
    small = svc.history(db, world.user, limit=2, clock=clock)
    assert [i.id for i in small.items] == [third, second] and small.next_before_id == second
    rest = svc.history(db, world.user, limit=2, before_id=small.next_before_id, clock=clock)
    assert [i.id for i in rest.items] == [first] and rest.next_before_id is None
    assert [i.id for i in svc.history(db, world.user, job_id=world.job_id, clock=clock).items] == [third, second, first]
    assert svc.history(db, world.user, job_id=other_job.job_id, clock=clock).items == ()


def test_the_history_page_size_is_clamped(db, world, clock):
    for _ in range(3):
        add(db, world, clock, S.COMPLETED)
    assert len(svc.history(db, world.user, limit=0, clock=clock).items) == 1
    assert len(svc.history(db, world.user, limit=-5, clock=clock).items) == 1
    assert len(svc.history(db, world.user, limit=10_000, clock=clock).items) == 3
    assert len(svc.history(db, world.user, clock=clock).items) == 3


def test_a_session_of_a_job_that_closed_is_still_in_the_history(db, world, clock):
    from app.models import JobPosting

    session_id = add(db, world, clock, S.COMPLETED)
    db.get(JobPosting, world.job_id).status = "closed"
    db.commit()
    assert [i.id for i in svc.history(db, world.user, job_id=world.job_id, clock=clock).items] == [session_id]


def test_a_feedback_is_reported_as_ready_and_otherwise_none(db, world, clock):
    ready = add(db, world, clock, S.COMPLETED, feedback={"topics": []}, feedback_method="rules")
    none = add(db, world, clock, S.COMPLETED)
    status = {i.id: i.feedback_status for i in svc.history(db, world.user, clock=clock).items}
    assert status == {ready: "ready", none: "none"}
    assert svc.detail(db, world.user, ready, clock=clock).feedback_status == "ready"


# ── End ──


def test_end_aborts_with_the_seekers_reason_and_is_idempotent(db, world, clock):
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    clock.advance(10)
    view = svc.end(db, world.user, session_id, clock=clock)
    assert (view.status, view.end_reason, view.active_until, view.ended_at) == ("aborted", "seeker_ended", None, clock())
    status, reason, ended_at, active_until, _ = physical(db, session_id)
    assert (status, reason, active_until) == ("aborted", "seeker_ended", None)
    clock.advance(500)
    again = svc.end(db, world.user, session_id, clock=clock)
    assert (again.status, again.end_reason, again.ended_at) == ("aborted", "seeker_ended", view.ended_at)  # unchanged


def test_end_of_a_live_session_is_possible_until_it_is_stale(db, world, clock):
    session_id = add(db, world, clock, S.LIVE, deadline=600)
    clock.advance(610)  # past the time budget, inside the grace: still live
    assert svc.end(db, world.user, session_id, clock=clock).end_reason == "seeker_ended"
    stale = add(db, world, clock, S.LIVE, deadline=600)
    clock.advance(700)
    assert svc.end(db, world.user, stale, clock=clock).end_reason == "stale_live"  # too late: it already went stale


def test_end_leaves_a_completed_session_as_it_is(db, world, clock):
    session_id = add(db, world, clock, S.COMPLETED, end_reason="plan_exhausted", ended_at=clock())
    view = svc.end(db, world.user, session_id, clock=clock)
    assert (view.status, view.end_reason) == ("completed", "plan_exhausted")


def test_end_of_a_session_nobody_joined_keeps_its_reason_and_settles_it(db, world, clock):
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    clock.advance(400)
    view = svc.end(db, world.user, session_id, clock=clock)
    assert (view.status, view.end_reason) == ("aborted", "not_joined")  # not rewritten as seeker_ended
    assert physical(db, session_id)[:2] == ("aborted", "not_joined")  # End settles


def test_end_of_a_session_still_being_planned_is_refused_and_a_lost_one_is_settled(db, world, clock):
    session_id = add(db, world, clock, S.PLANNING, deadline=120)
    refuse(lambda: svc.end(db, world.user, session_id, clock=clock), 409, "INTERVIEW_PLANNING")
    assert physical(db, session_id)[0] == S.PLANNING
    clock.advance(130)
    view = svc.end(db, world.user, session_id, clock=clock)
    assert (view.status, view.end_reason) == ("aborted", "planning_lost")


def test_end_never_touches_the_quota(db, world, clock):
    assert quota.claim(db, world.user.id, QuotaKind.SESSION, now=clock())
    db.commit()
    before = quota_rows(db)
    svc.end(db, world.user, add(db, world, clock, S.CREATED, deadline=300), clock=clock)
    assert quota_rows(db) == before


# ── Delete ──


def test_delete_removes_the_session_and_its_turns_in_any_status_and_keeps_the_quota(db, world, clock):
    assert quota.claim(db, world.user.id, QuotaKind.SESSION, now=clock())
    db.commit()
    before = quota_rows(db)
    for status, deadline in ((S.PLANNING, 120), (S.CREATED, 300), (S.LIVE, 600), (S.COMPLETED, None), (S.ABORTED, None)):
        session_id = add(db, world, clock, status, deadline=deadline)
        db.add(InterviewTurn(session_id=session_id, seq=1, role="candidate", kind="answer", text="답변"))
        db.commit()
        svc.delete(db, world.user, session_id, clock=clock)
        refuse(lambda: svc.detail(db, world.user, session_id, clock=clock), 404, "INTERVIEW_NOT_FOUND")
        refuse(lambda: svc.delete(db, world.user, session_id, clock=clock), 404, "INTERVIEW_NOT_FOUND")
    assert db.scalar(select(func.count()).select_from(InterviewSession)) == 0
    assert db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
    assert quota_rows(db) == before


# ── Settlement ──


@pytest.mark.parametrize("status, deadline, later", [(s, d, t) for s, d, t, _ in OVERLAY])
def test_settlement_does_what_the_overlay_shows(db, world, clock, status, deadline, later):
    """The row says, after `settle`, exactly what the derived view said before it: the same thresholds."""
    session_id = add(db, world, clock, status, deadline=deadline)
    clock.advance(later)
    shown = svc.detail(db, world.user, session_id, clock=clock)
    changed = svc.settle(db, world.user.id, clock())
    status_now, reason_now, ended_at, active_until, _ = physical(db, session_id)
    assert changed == (1 if shown.status == S.ABORTED else 0)
    assert (status_now, reason_now) == (shown.status, shown.end_reason)
    if shown.status == S.ABORTED:
        assert as_utc(ended_at) == shown.ended_at and active_until is None  # the deadline it missed, not the time of settling
    assert svc.settle(db, world.user.id, clock()) == 0  # idempotent
    after = svc.detail(db, world.user, session_id, clock=clock)
    assert (after.status, after.end_reason, after.joinable, after.accepting_turns, after.end_grace_open) == (shown.status, shown.end_reason, shown.joinable, shown.accepting_turns, shown.end_grace_open)


def test_settling_one_seeker_leaves_the_others_alone_and_everyone_settles_for_the_script(db, world, clock):
    other = build_world(db, email="other@interview.test")
    mine = add(db, world, clock, S.CREATED, deadline=300)
    theirs = add(db, other, clock, S.CREATED, deadline=300)
    clock.advance(301)
    assert svc.settle(db, world.user.id, clock()) == 1
    assert (physical(db, mine)[0], physical(db, theirs)[0]) == (S.ABORTED, S.CREATED)
    assert svc.settle(db, None, clock()) == 1
    assert physical(db, theirs)[:2] == (S.ABORTED, "not_joined")


def test_settlement_never_refunds_the_quota(db, world, clock):
    assert quota.claim(db, world.user.id, QuotaKind.SESSION, now=clock()) and quota.claim(db, world.user.id, QuotaKind.PLAN_MODEL, now=clock())
    db.commit()
    before = quota_rows(db)
    add(db, world, clock, S.PLANNING, deadline=120)
    clock.advance(1000)
    assert svc.settle(db, None, clock()) == 1
    assert quota_rows(db) == before


def test_a_row_without_a_deadline_is_settled_too(db, world, clock):
    session_id = add(db, world, clock, S.CREATED)  # no active_until: should never happen, and must not stay active
    assert svc.settle(db, world.user.id, clock()) == 1
    assert physical(db, session_id)[:2] == (S.ABORTED, "not_joined")
