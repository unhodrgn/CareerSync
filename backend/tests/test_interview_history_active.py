"""`HistoryPage.active` (M4 S4.3; docs/DECISIONS.md D67 (3)): the seeker's one planning, created or live session, as the service finds it.

`interview_service.history` returns it next to the items. It is derived at the same `now` as the items (`interview_time.derive`), it does not
depend on `job_id`, `limit` or `before_id`, and it is a read: a session past its deadline reads `aborted` and is not active, and no row is
settled, no quota is touched and no model is called. The HTTP cases of the same rule are in test_interview_api_history.py, which also uses the
helpers and the lifecycle table of this module."""
import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import InterviewQuota, InterviewSession, JobPosting
from app.models.interview import InterviewStatus as S
from app.services import interview_service as svc

from .interview_fixtures import Clock, Ids, build_world, make_session

TABLE = InterviewSession.__table__
GRACE = settings.INTERVIEW_END_GRACE_SECONDS

# (label, stored status, seconds from now to `active_until`, seconds the clock moves, the derived status of the active session or None).
# A deadline is inclusive: a session is stale only after it, and a live one only after the end grace.
CASES = [
    ("planning, lease valid", S.PLANNING, 120, 0, "planning"),
    ("planning, on the end of its lease", S.PLANNING, 120, 120, "planning"),
    ("planning, lease passed", S.PLANNING, 120, 120.001, None),
    ("created, before the join deadline", S.CREATED, 300, 10, "created"),
    ("created, on the join deadline", S.CREATED, 300, 300, "created"),
    ("created, join deadline passed", S.CREATED, 300, 300.001, None),
    ("live, in its budget", S.LIVE, 600, 100, "live"),
    ("live, on the end of its budget", S.LIVE, 600, 600, "live"),
    ("live, in the end grace", S.LIVE, 600, 600.001, "live"),
    ("live, on the end of the grace", S.LIVE, 600, 600 + GRACE, "live"),
    ("live, past the grace", S.LIVE, 600, 600 + GRACE + 0.001, None),
    ("completed", S.COMPLETED, None, 0, None),
    ("aborted", S.ABORTED, None, 0, None),
]
# What a stale row reads as, by its stored status
STALE_REASON = {S.PLANNING: "planning_lost", S.CREATED: "not_joined", S.LIVE: "stale_live"}


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def ids_of(world) -> Ids:
    return Ids(world.user.id, world.job_id, world.cv_profile_id)


def add(db, world, clock, status=S.CREATED, *, deadline=None, expires_in=30 * 86400, **overrides):
    """A session row as the lifecycle would have left it, `deadline` seconds after the clock's now. `job_id=` puts it on another job."""
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


def new_job(db, world) -> int:
    """A second job of the same company, for the seeker of `world`."""
    job = JobPosting(company_id=db.get(JobPosting, world.job_id).company_id, title="Data Engineer", description="Python")
    db.add(job)
    db.commit()
    return job.id


def physical(db, session_id):
    """What the row itself says (not an ORM object, so nothing cached)."""
    return tuple(db.execute(select(TABLE.c.status, TABLE.c.end_reason, TABLE.c.ended_at, TABLE.c.active_until, TABLE.c.expires_at).where(TABLE.c.id == session_id)).one())


def quota_rows(db):
    return sorted(tuple(r) for r in db.execute(select(InterviewQuota.seeker_id, InterviewQuota.kst_day, InterviewQuota.kind, InterviewQuota.used, InterviewQuota.quota_limit)))


# ── The page ──


def test_the_page_has_exactly_the_items_the_cursor_and_the_active_session():
    assert [f.name for f in dataclasses.fields(svc.HistoryPage)] == ["items", "next_before_id", "active"]


def test_a_seeker_with_no_session_has_an_empty_page_and_no_active_session(db, world, clock):
    page = svc.history(db, world.user, clock=clock)
    assert page.items == () and page.next_before_id is None and page.active is None


# ── Which session is active ──


@pytest.mark.parametrize("label, status, deadline, advance, expected", CASES, ids=[case[0] for case in CASES])
def test_the_active_session_is_the_one_whose_derived_status_is_still_active(db, world, clock, label, status, deadline, advance, expected):
    session_id = add(db, world, clock, status, deadline=deadline)
    stored = physical(db, session_id)
    clock.advance(advance)
    page = svc.history(db, world.user, clock=clock)
    if expected is None:
        assert page.active is None
    else:
        assert (page.active.id, page.active.status) == (session_id, expected)
    assert physical(db, session_id) == stored  # a read never settles a row


@pytest.mark.parametrize("status", [S.PLANNING, S.CREATED, S.LIVE])
def test_a_stale_session_reads_aborted_with_its_reason_and_is_not_active(db, world, clock, status):
    session_id = add(db, world, clock, status, deadline=-1 - (GRACE if status == S.LIVE else 0))
    stored = physical(db, session_id)
    page = svc.history(db, world.user, clock=clock)
    assert page.active is None
    assert [(i.id, i.status, i.end_reason, i.joinable) for i in page.items] == [(session_id, "aborted", STALE_REASON[status], False)]
    assert physical(db, session_id) == stored and stored[0] == status  # the row still says what it said


def test_only_a_created_session_is_joinable_and_a_planning_one_is_not(db, world, clock):
    planning = add(db, world, clock, S.PLANNING, deadline=120)
    assert (svc.history(db, world.user, clock=clock).active.id, svc.history(db, world.user, clock=clock).active.joinable) == (planning, False)
    db.execute(TABLE.update().where(TABLE.c.id == planning).values(status=S.CREATED, active_until=clock() + timedelta(seconds=300)))
    db.commit()
    assert svc.history(db, world.user, clock=clock).active.joinable is True


def test_a_session_of_a_job_that_closed_is_still_active(db, world, clock):
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    db.get(JobPosting, world.job_id).status = "closed"
    db.commit()
    page = svc.history(db, world.user, clock=clock)
    assert page.active.id == session_id and page.active.job_title == "Backend Engineer"


# ── Independence from the page ──


def test_the_active_session_does_not_depend_on_limit(db, world, clock):
    active = add(db, world, clock, S.CREATED, deadline=300)  # the oldest row, so no page of one reaches it
    newer = [add(db, world, clock, S.COMPLETED) for _ in range(3)]
    page = svc.history(db, world.user, limit=1, clock=clock)
    assert [i.id for i in page.items] == [newer[-1]] and page.active.id == active


def test_the_active_session_does_not_depend_on_before_id(db, world, clock):
    first = add(db, world, clock, S.COMPLETED)
    active = add(db, world, clock, S.CREATED, deadline=300)
    page = svc.history(db, world.user, before_id=active, clock=clock)
    assert [i.id for i in page.items] == [first] and page.active.id == active  # not in the items, still active
    page = svc.history(db, world.user, before_id=first, clock=clock)
    assert page.items == () and page.active.id == active


def test_the_active_session_does_not_depend_on_job_id(db, world, clock):
    other = new_job(db, world)
    active = add(db, world, clock, S.CREATED, deadline=300)
    done_elsewhere = add(db, world, clock, S.COMPLETED, job_id=other)
    page = svc.history(db, world.user, job_id=other, clock=clock)
    assert [i.id for i in page.items] == [done_elsewhere] and page.active.id == active and page.active.job_id == world.job_id
    for job_id in (999_999, 0, -1):  # a job nobody has, and ids that cannot exist: an empty page, the active session all the same
        page = svc.history(db, world.user, job_id=job_id, clock=clock)
        assert page.items == () and page.active.id == active, job_id


def test_an_active_session_on_the_page_is_the_same_summary_in_the_items_and_in_active(db, world, clock):
    add(db, world, clock, S.COMPLETED)
    active = add(db, world, clock, S.LIVE, deadline=600)
    page = svc.history(db, world.user, clock=clock)
    assert page.items[0].id == active and page.active == page.items[0]
    small = svc.history(db, world.user, limit=1, clock=clock)
    assert small.active == small.items[0]


# ── Ownership, retention, and what a read does not do ──


def test_another_seekers_session_is_never_returned(db, world, clock):
    other = build_world(db, email="two@interview.test")
    theirs = add(db, other, clock, S.CREATED, deadline=300)
    assert svc.history(db, world.user, clock=clock).active is None
    mine = add(db, world, clock, S.CREATED, deadline=300)
    assert svc.history(db, world.user, clock=clock).active.id == mine
    assert svc.history(db, other.user, clock=clock).active.id == theirs


def test_an_expired_session_is_not_active_and_the_seekers_own_one_is_purged(db, world, clock):
    expired = add(db, world, clock, S.CREATED, deadline=1000, expires_in=100)  # its deadline is far away, its expiry is not
    clock.advance(99.999)
    assert svc.history(db, world.user, clock=clock).active.id == expired
    clock.advance(0.001)  # `expires_at` is the instant it goes
    page = svc.history(db, world.user, clock=clock)
    assert page.active is None and page.items == ()
    assert db.execute(select(InterviewSession.id).where(InterviewSession.id == expired)).first() is None  # the lazy purge of D65


def test_looking_up_the_active_session_writes_no_status_takes_no_quota_and_calls_no_model(db, world, clock, monkeypatch):
    from app.services import ai_runtime

    def boom(*args, **kwargs):
        raise AssertionError("the history reached a model or an embedder")

    monkeypatch.setattr(ai_runtime, "llm", boom)
    monkeypatch.setattr(ai_runtime, "embedder", boom)
    stale = add(db, world, clock, S.CREATED, deadline=-5)
    stored = physical(db, stale)
    assert quota_rows(db) == []
    svc.history(db, world.user, clock=clock)
    assert physical(db, stale) == stored and quota_rows(db) == []
