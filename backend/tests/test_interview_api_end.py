"""`POST /api/interview-sessions/{session_id}/end` (M4 S4.4; docs/DECISIONS.md D67, D69): the seeker ends a practice interview.

The route calls `interview_service.end` and adds nothing, so these tests show that the HTTP layer keeps the service's contract: 200 with the
`SessionOut` of the session as it is after the call; a `created` session up to its join deadline and a `live` one up to its deadline plus the
end grace become `aborted` with the reason `seeker_ended`; a session past that keeps the reason it was settled with; a session being
planned is a 409 `INTERVIEW_PLANNING`; a repeated End changes nothing. The service settles the seeker's own stale sessions before it looks
the session up, so that happens before a 404 as well. The seeker's End writes no closing line and no end event, calls no model and touches no
quota: the agent's final event is M5 (`interview_ingest_service.record_end`, which these tests make fail if anything calls it). What the End has
in common with the other routes of the session is in test_interview_api_session_common.py; the agent's side of "the seeker ended it" is in
test_interview_ingest_end.py. Time is the test clock, and the database is the SQLite fixture."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.models.interview import InterviewStatus as S
from app.models.interview import QuotaKind
from app.services import interview_ingest_service, interview_service
from app.services import interview_quota_service as quota_service
from app.services.interview_time import as_utc

from .conftest import auth
from .interview_fixtures import build_world
from .test_interview_api_create import SESSION_KEYS
from .test_interview_api_session_common import DETAIL, END, URL, api, call, clock, no_store, no_wall_clock  # noqa: F401 (the fixtures)
from .test_interview_history_active import add, physical, quota_rows

GRACE = settings.INTERVIEW_END_GRACE_SECONDS
SECRET = "SECRET-MARKER-답변-내용"
VALID = {"consent_transcript": True, "consent_version": settings.INTERVIEW_CONSENT_VERSION}

# (label, stored status, seconds from now to `active_until`, seconds the clock moves, HTTP status, status after, reason after, when it ended).
# `now` is the time of the request, `deadline` the deadline the session missed. A deadline is inclusive: stale only after it, a live one only
# after the end grace.
LIFECYCLE = [
    ("planning, lease valid", S.PLANNING, 120, 0, 409, None, None, None),
    ("planning, on the end of its lease", S.PLANNING, 120, 120, 409, None, None, None),
    ("planning, lease passed", S.PLANNING, 120, 120.001, 200, "aborted", "planning_lost", "deadline"),
    ("created, within the join deadline", S.CREATED, 300, 10, 200, "aborted", "seeker_ended", "now"),
    ("created, on the join deadline", S.CREATED, 300, 300, 200, "aborted", "seeker_ended", "now"),
    ("created, 0.001 s past the join deadline", S.CREATED, 300, 300.001, 200, "aborted", "not_joined", "deadline"),
    ("live, in its budget", S.LIVE, 600, 100, 200, "aborted", "seeker_ended", "now"),
    ("live, on the end of its budget", S.LIVE, 600, 600, 200, "aborted", "seeker_ended", "now"),
    ("live, 0.001 s into the end grace", S.LIVE, 600, 600.001, 200, "aborted", "seeker_ended", "now"),
    ("live, in the middle of the end grace", S.LIVE, 600, 600 + GRACE / 2, 200, "aborted", "seeker_ended", "now"),
    ("live, on the end of the end grace", S.LIVE, 600, 600 + GRACE, 200, "aborted", "seeker_ended", "now"),
    ("live, 0.001 s past the end grace", S.LIVE, 600, 600 + GRACE + 0.001, 200, "aborted", "stale_live", "deadline"),
]


def end(api, world, session_id):
    return call(api, END, session_id, world.user)


def detail(api, world, session_id):
    return call(api, DETAIL, session_id, world.user)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def turn_count(db) -> int:
    return db.scalar(select(func.count()).select_from(InterviewTurn))


def create(api, world) -> dict:
    created = api.post(f"/api/jobs/{world.job_id}/interview-sessions", headers=auth(world.user), json=VALID)
    assert created.status_code == 201, created.text
    return created.json()["session"]


def row_after(db, session_id):
    """(status, end_reason, ended_at as UTC, active_until) as the row says now."""
    status, reason, ended_at, active_until, _expires = physical(db, session_id)
    return status, reason, as_utc(ended_at), active_until


# ── The lifecycle, with exact boundaries ──


@pytest.mark.parametrize("label, status, deadline, advance, http, after, reason, when", LIFECYCLE, ids=[case[0] for case in LIFECYCLE])
def test_end_follows_the_lifecycle_with_exact_boundaries(api, db, clock, label, status, deadline, advance, http, after, reason, when):
    world = build_world(db)
    session_id = add(db, world, clock, status, deadline=deadline)
    start = clock.now
    stored = physical(db, session_id)
    clock.advance(advance)
    quota_before = quota_rows(db)
    response = end(api, world, session_id)
    assert no_store(response) and response.status_code == http, response.text
    assert turn_count(db) == 0 and quota_rows(db) == quota_before  # no closing line, no end event, no quota
    if http == 409:  # still being planned: refused, and nothing changed
        body = response.json()
        assert set(body) == {"code", "message"} and body["code"] == "INTERVIEW_PLANNING" and body["message"], body
        assert physical(db, session_id) == stored
        return
    body = response.json()
    assert set(body) == SESSION_KEYS and (body["status"], body["end_reason"]) == (after, reason)
    ended = clock.now if when == "now" else start + timedelta(seconds=deadline)
    assert at(body["ended_at"]) == ended
    assert (body["active_until"], body["joinable"], body["accepting_turns"], body["end_grace_open"]) == (None, False, False, False)
    assert row_after(db, session_id) == (after, reason, ended, None)  # and the row says it too
    assert detail(api, world, session_id).json() == body  # the End returned the session as it is now


def test_a_session_ended_by_the_seeker_has_its_own_started_at_untouched(api, db, clock):
    world = build_world(db)
    live = add(db, world, clock, S.LIVE, deadline=600)  # `add` starts a live session at the clock's now
    started = clock.now
    clock.advance(100)
    body = end(api, world, live).json()
    assert at(body["started_at"]) == started and at(body["ended_at"]) == clock.now and body["max_seconds"] == settings.INTERVIEW_MAX_SECONDS


def test_the_200_of_a_created_session_matches_the_session_schema_and_keeps_its_plan_topics(api, db, clock):
    world = build_world(db)
    session = create(api, world)
    clock.advance(30)
    response = end(api, world, session["id"])
    assert response.status_code == 200 and no_store(response) and response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == SESSION_KEYS and body["notice"] == session["notice"]
    assert (body["status"], body["end_reason"], body["started_at"], body["turns"]) == ("aborted", "seeker_ended", None, [])
    assert body["topics"] == session["topics"] and body["plan_method"] == session["plan_method"]  # the plan is not touched
    assert at(body["ended_at"]) == clock.now and body["expires_at"] == session["expires_at"]  # and the expiry is never extended


# ── Idempotency ──


@pytest.mark.parametrize(
    "status, deadline, advance",
    [(S.CREATED, 300, 10), (S.CREATED, 300, 400), (S.LIVE, 600, 610), (S.LIVE, 600, 700)],
    ids=["created, ended by the seeker", "created, settled as not_joined", "live in the grace, ended by the seeker", "live, settled as stale_live"],
)
def test_a_repeated_end_returns_the_same_session_with_the_first_ended_at(api, db, clock, status, deadline, advance):
    world = build_world(db)
    session_id = add(db, world, clock, status, deadline=deadline)
    clock.advance(advance)
    first = end(api, world, session_id)
    assert first.status_code == 200
    stored = physical(db, session_id)
    for seconds in (1, 500, 86_400):
        clock.advance(seconds)
        again = end(api, world, session_id)
        assert again.status_code == 200 and no_store(again) and again.json() == first.json(), seconds
        assert physical(db, session_id) == stored  # nothing is rewritten: neither the reason nor `ended_at`


def test_a_completed_or_an_already_aborted_session_is_returned_as_it_is(api, db, clock):
    world = build_world(db)
    done = add(db, world, clock, S.COMPLETED, end_reason="plan_exhausted", ended_at=clock())
    gone = add(db, world, clock, S.ABORTED, end_reason="not_joined", ended_at=clock())
    clock.advance(1000)
    for session_id, status, reason in ((done, "completed", "plan_exhausted"), (gone, "aborted", "not_joined")):
        stored = physical(db, session_id)
        body = end(api, world, session_id).json()
        assert (body["status"], body["end_reason"]) == (status, reason) and physical(db, session_id) == stored
        assert at(body["ended_at"]) < clock.now  # the time it ended, not now


def test_a_body_that_is_sent_is_ignored(api, db, clock):
    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    response = call(api, END, session_id, world.user, json={"end_reason": SECRET, SECRET: SECRET})
    assert response.status_code == 200 and no_store(response) and SECRET not in response.text
    assert row_after(db, session_id)[:2] == ("aborted", "seeker_ended")  # the reason is the route's, not the client's


# ── What the End does not do ──


def test_the_end_writes_no_closing_line_and_no_end_event_and_leaves_the_plan_and_the_coverage(api, db, clock, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the seeker's End reached the ingestion of the agent's events (M5)")

    monkeypatch.setattr(interview_ingest_service, "record_end", boom)
    monkeypatch.setattr(interview_ingest_service, "record_turn", boom)
    world = build_world(db)
    plan, coverage = {"items": []}, {"phase": "listening", "status": {"c1": "asked"}, "levels": {}}
    session_id = add(db, world, clock, S.LIVE, deadline=600, plan=plan, coverage=coverage)
    db.add(InterviewTurn(session_id=session_id, seq=1, role="agent", kind="question", text="자기소개를 해 주세요."))
    db.add(InterviewTurn(session_id=session_id, seq=2, role="candidate", kind="answer", text="저는 [이름]입니다."))
    db.commit()
    turns = [tuple(t) for t in db.execute(select(InterviewTurn.seq, InterviewTurn.role, InterviewTurn.kind, InterviewTurn.text).order_by(InterviewTurn.seq))]
    clock.advance(100)
    response = end(api, world, session_id)
    assert response.status_code == 200 and response.json()["end_reason"] == "seeker_ended"
    db.expire_all()
    assert [tuple(t) for t in db.execute(select(InterviewTurn.seq, InterviewTurn.role, InterviewTurn.kind, InterviewTurn.text).order_by(InterviewTurn.seq))] == turns
    assert not db.scalar(select(func.count()).select_from(InterviewTurn).where(InterviewTurn.kind == "closing"))  # no closing line
    row = db.get(InterviewSession, session_id)
    assert (row.plan, row.coverage, row.feedback) == (plan, coverage, None)  # and no final coverage snapshot (that is the agent's event)
    assert [(t["seq"], t["kind"]) for t in response.json()["turns"]] == [(1, "question"), (2, "answer")]


def test_the_end_changes_no_quota_and_calls_no_model(api, db, clock, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the End reached a model or an embedder")

    from app.services import ai_runtime

    monkeypatch.setattr(ai_runtime, "llm", boom)
    monkeypatch.setattr(ai_runtime, "embedder", boom)
    world = build_world(db)
    assert quota_service.claim(db, world.user.id, QuotaKind.SESSION, now=clock())
    db.commit()
    before = quota_rows(db)
    assert before and before[0][3] == 1  # one reservation is used
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    assert end(api, world, session_id).status_code == 200
    assert quota_rows(db) == before  # nothing is refunded and nothing is taken


def test_the_end_does_not_purge_an_expired_session(api, db, clock):
    world = build_world(db)
    expired = add(db, world, clock, S.COMPLETED, expires_in=-1)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    assert end(api, world, session_id).status_code == 200
    db.expire_all()
    assert db.get(InterviewSession, expired) is not None  # only create, history and delete purge (D65)


# ── Who is settled ──


def stale_created(db, world, clock):
    """A `created` session of `world` whose join deadline is 1 second behind the clock: stored `created`, read as `aborted`."""
    return add(db, world, clock, S.CREATED, deadline=-1)


@pytest.mark.parametrize("target", ["a completed session of the seeker", "an unknown id", "another seekers session"])
def test_the_end_settles_the_seekers_other_stale_session_before_it_answers_even_a_404(api, db, clock, target):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    stale = stale_created(db, world, clock)
    done = add(db, world, clock, S.COMPLETED, end_reason="plan_exhausted", ended_at=clock())
    theirs = add(db, other, clock, S.COMPLETED)
    asked, http = {"a completed session of the seeker": (done, 200), "an unknown id": (999_999, 404), "another seekers session": (theirs, 404)}[target]
    assert physical(db, stale)[:2] == (S.CREATED, None)  # stored as created
    response = end(api, world, asked)
    assert response.status_code == http and no_store(response)
    status, reason, ended_at, active_until = row_after(db, stale)
    assert (status, reason, active_until) == ("aborted", "not_joined", None)  # settled, with the deadline it missed
    assert ended_at == clock.now - timedelta(seconds=1)  # the join deadline it missed (the clock has not moved since `stale_created`)
    if http == 200:
        assert response.json()["end_reason"] == "plan_exhausted"  # the session asked for is returned as it is


def test_the_end_of_one_seeker_settles_nothing_of_another(api, db, clock):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    mine = add(db, world, clock, S.CREATED, deadline=300)
    their_stale = stale_created(db, other, clock)
    their_live = add(db, build_world(db, email="three@interview.test"), clock, S.LIVE, deadline=600)
    db.add(InterviewTurn(session_id=their_live, seq=1, role="agent", kind="question", text="질문"))
    db.commit()
    stored = (physical(db, their_stale), physical(db, their_live), turn_count(db))
    assert end(api, world, mine).status_code == 200
    assert (physical(db, their_stale), physical(db, their_live), turn_count(db)) == stored  # their stale session is still stored as created
    assert physical(db, their_stale)[0] == S.CREATED


# ── After the End ──


def test_after_the_end_the_history_has_no_active_session_and_shows_the_session_as_aborted(api, db, clock):
    world = build_world(db)
    session_id = create(api, world)["id"]
    before = api.get(URL, headers=auth(world.user)).json()
    assert before["active"]["id"] == session_id
    clock.advance(20)
    assert end(api, world, session_id).status_code == 200
    after = api.get(URL, headers=auth(world.user)).json()
    assert after["active"] is None
    assert [(i["id"], i["status"], i["end_reason"], i["joinable"]) for i in after["items"]] == [(session_id, "aborted", "seeker_ended", False)]


# ── A failure ──


def test_when_the_database_fails_the_end_changes_nothing_and_the_answer_is_a_500_with_no_store(api, db, clock, monkeypatch):
    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    stored = physical(db, session_id)
    real_commit, calls = db.commit, {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 2:  # the first commit is the settlement, the second is the End's own update
            raise RuntimeError("the database went away")
        return real_commit()

    monkeypatch.setattr(db, "commit", flaky)
    response = end(api, world, session_id)
    assert calls["n"] == 2 and response.status_code == 500 and no_store(response)
    assert "went away" not in response.text  # no detail of the failure
    db.rollback()  # what closing the session does at the end of a real request (`get_db`)
    assert physical(db, session_id) == stored  # still `created`, with its deadline: nothing is half done
    assert turn_count(db) == 0
