"""`DELETE /api/interview-sessions/{session_id}` (M4 S4.4; docs/DECISIONS.md D53, D64, D65, D67, D69): the seeker deletes a practice interview.

The route calls `interview_service.delete` and adds nothing, so these tests show that the HTTP layer keeps the service's contract: 204 with an
empty body; the session, its turns and its stored feedback go together, in one transaction, in any status; the quota is not refunded; other
sessions, of the same seeker and of others, are untouched; the seeker's own expired sessions are purged before the lookup (and no one else's);
a delete is final, so a repeat is a 404 `INTERVIEW_NOT_FOUND` and changes nothing; a failure rolls everything back. Deleting a live session only
removes its rows: nothing here notifies or disconnects an agent (M5), and the agent's next event for that session is refused by the ingestion
as a 404, which the last test shows. What the delete has in common with the other routes of the session is in
test_interview_api_session_common.py. Time is the test clock, and the database is the SQLite fixture."""
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn
from app.models.interview import InterviewStatus as S
from app.models.interview import QuotaKind
from app.services import interview_ingest_service as ingest
from app.services import interview_quota_service as quota_service

from .conftest import auth
from .interview_fixtures import build_world
from .test_interview_api_session_common import DELETE, DETAIL, URL, api, call, clock, no_store, no_wall_clock  # noqa: F401 (the fixtures)
from .test_interview_create import capture
from .test_interview_history_active import add, quota_rows

SECRET = "SECRET-MARKER-답변-내용"
FEEDBACK_MARKER = "FEEDBACK-MARKER"
VALID = {"consent_transcript": True, "consent_version": settings.INTERVIEW_CONSENT_VERSION}
STATUSES = [("planning", S.PLANNING, 120), ("created", S.CREATED, 300), ("live", S.LIVE, 600), ("completed", S.COMPLETED, None), ("aborted", S.ABORTED, None)]


def delete(api, world, session_id):
    return call(api, DELETE, session_id, world.user)


def seed(db, world, clock, status, deadline, *, turns=2, feedback=False, **kwargs):
    """A session of `world` in `status` with `turns` turns and, if asked, a stored feedback."""
    if feedback:
        kwargs.update(feedback={"topics": [], "marker": FEEDBACK_MARKER}, feedback_method="rules")
    session_id = add(db, world, clock, status, deadline=deadline, **kwargs)
    for seq in range(1, turns + 1):
        agent = seq % 2 == 1
        db.add(InterviewTurn(session_id=session_id, seq=seq, role="agent" if agent else "candidate", kind="question" if agent else "answer", text=f"발화 {seq}"))
    db.commit()
    return session_id


def state_of(db, *ids):
    """{id: (the row as stored, with its feedback; its turns)}. A session that is gone is (None, [])."""
    out = {}
    for session_id in ids:
        row = db.execute(
            select(
                InterviewSession.status, InterviewSession.end_reason, InterviewSession.active_until, InterviewSession.expires_at,
                InterviewSession.feedback, InterviewSession.feedback_method,
            ).where(InterviewSession.id == session_id)
        ).first()
        turns = [tuple(t) for t in db.execute(select(InterviewTurn.seq, InterviewTurn.role, InterviewTurn.kind, InterviewTurn.text).where(InterviewTurn.session_id == session_id).order_by(InterviewTurn.seq))]
        out[session_id] = (None if row is None else tuple(row), turns)
    return out


def create(api, world) -> dict:
    created = api.post(f"/api/jobs/{world.job_id}/interview-sessions", headers=auth(world.user), json=VALID)
    assert created.status_code == 201, created.text
    return created.json()["session"]


def claim_one(db, world, clock):
    assert quota_service.claim(db, world.user.id, QuotaKind.SESSION, now=clock())
    db.commit()
    return quota_rows(db)


# ── Any status, with its turns and feedback; a repeat is a 404 ──


@pytest.mark.parametrize("label, status, deadline", STATUSES, ids=[case[0] for case in STATUSES])
def test_a_session_is_deleted_in_any_status_with_its_turns_and_feedback_and_a_repeat_is_a_404(api, db, clock, label, status, deadline):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    quota_before = claim_one(db, world, clock)
    target = seed(db, world, clock, status, deadline, feedback=status in (S.COMPLETED, S.ABORTED))
    kept = seed(db, world, clock, S.COMPLETED, None, turns=1, feedback=True)  # the seeker's own other session
    theirs = seed(db, other, clock, S.LIVE, 600, turns=1)  # another seeker's, and live
    others_before = state_of(db, kept, theirs)
    row, turns = state_of(db, target)[target]
    assert row is not None and len(turns) == 2 and (row[4] is not None) == (status in (S.COMPLETED, S.ABORTED))  # what is about to go

    first = delete(api, world, target)
    assert first.status_code == 204 and first.content == b"" and no_store(first), first.text
    assert state_of(db, target)[target] == (None, [])  # neither the session, nor its feedback, nor a turn of it is left
    assert state_of(db, kept, theirs) == others_before and quota_rows(db) == quota_before  # nothing else changed, nothing refunded
    assert call(api, DETAIL, target, world.user).status_code == 404
    page = api.get(URL, headers=auth(world.user)).json()
    assert [item["id"] for item in page["items"]] == [kept] and page["active"] is None  # the history no longer has it, nor an active session

    for _ in range(2):  # a delete is final
        again = delete(api, world, target)
        body = again.json()
        assert again.status_code == 404 and no_store(again) and set(body) == {"code", "message"} and body["code"] == "INTERVIEW_NOT_FOUND"
    assert state_of(db, kept, theirs) == others_before and quota_rows(db) == quota_before  # and a repeat changed nothing


def test_the_feedback_goes_with_the_session(api, db, clock):
    world = build_world(db)
    with_feedback = seed(db, world, clock, S.COMPLETED, None, feedback=True)
    kept = seed(db, world, clock, S.COMPLETED, None, feedback=True)
    assert delete(api, world, with_feedback).status_code == 204
    left = db.execute(select(InterviewSession.id).where(InterviewSession.feedback.is_not(None))).scalars().all()
    assert left == [kept]  # no feedback of the deleted session is kept anywhere


def test_a_body_that_is_sent_is_ignored(api, db, clock):
    world = build_world(db)
    session_id = seed(db, world, clock, S.COMPLETED, None)
    response = call(api, DELETE, session_id, world.user, json={SECRET: SECRET})
    assert response.status_code == 204 and response.content == b"" and no_store(response)
    assert state_of(db, session_id)[session_id] == (None, [])


# ── The quota ──


def test_deleting_frees_the_active_slot_but_refunds_no_quota(api, db, clock):
    world = build_world(db)

    def used() -> list[int]:
        return [row[3] for row in quota_rows(db) if row[2] == QuotaKind.SESSION]

    first = create(api, world)
    assert used() == [1]
    assert delete(api, world, first["id"]).status_code == 204
    assert used() == [1]  # the session still counts for the day (D64)
    assert api.get(URL, headers=auth(world.user)).json()["active"] is None
    second = create(api, world)  # the one-active-session slot is free at once (SQLite may give the new row the freed id, so the ids are not compared)
    assert api.get(URL, headers=auth(world.user)).json()["active"]["id"] == second["id"] and used() == [2]


# ── Retention: the seeker's own expired sessions are purged first, nobody else's ──


@pytest.mark.parametrize("target", ["an unknown id", "an expired session of the seeker", "another seekers session", "a live session of the seeker"])
def test_the_seekers_own_expired_sessions_are_purged_before_the_lookup_and_nobody_elses(api, db, clock, target):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    own_expired = [seed(db, world, clock, S.COMPLETED, None, turns=2, expires_in=-1) for _ in range(2)]
    their_expired = seed(db, other, clock, S.COMPLETED, None, turns=2, expires_in=-1)
    kept = seed(db, world, clock, S.COMPLETED, None, turns=1)
    live = seed(db, world, clock, S.LIVE, 600, turns=1)
    theirs = seed(db, other, clock, S.COMPLETED, None, turns=1)
    asked, http = {
        "an unknown id": (999_999, 404), "an expired session of the seeker": (own_expired[0], 404),
        "another seekers session": (theirs, 404), "a live session of the seeker": (live, 204),
    }[target]
    their_expired_before, theirs_before, kept_before = state_of(db, their_expired), state_of(db, theirs), state_of(db, kept)
    assert all(state_of(db, session_id)[session_id][0] is not None for session_id in own_expired)  # they are still stored

    response = delete(api, world, asked)
    assert response.status_code == http and no_store(response), response.text
    assert all(state_of(db, session_id)[session_id] == (None, []) for session_id in own_expired)  # purged with their turns, even before a 404
    assert state_of(db, their_expired) == their_expired_before and their_expired_before[their_expired][0] is not None  # another seeker's: untouched
    assert state_of(db, theirs) == theirs_before and state_of(db, kept) == kept_before
    assert (state_of(db, live)[live][0] is None) == (target == "a live session of the seeker")


# ── A failure ──


@pytest.mark.parametrize("failing", ["the delete of the session", "the final commit"])
def test_when_the_deletion_fails_nothing_is_deleted_and_the_answer_is_a_sanitized_500(api, db, clock, monkeypatch, failing):
    world = build_world(db)
    quota_before = claim_one(db, world, clock)
    target = seed(db, world, clock, S.COMPLETED, None, turns=3, feedback=True)
    sibling = seed(db, world, clock, S.ABORTED, None, turns=1)
    before = state_of(db, target, sibling)
    real_execute, real_commit = db.execute, db.commit

    def failing_execute(statement, *args, **kwargs):
        if str(statement).startswith("DELETE FROM interview_sessions"):
            raise RuntimeError(SECRET)
        return real_execute(statement, *args, **kwargs)

    def failing_commit():
        raise RuntimeError(SECRET)

    if failing == "the delete of the session":
        monkeypatch.setattr(db, "execute", failing_execute)
    else:
        monkeypatch.setattr(db, "commit", failing_commit)
    with capture(db) as log:
        response = delete(api, world, target)
    assert response.status_code == 500 and no_store(response) and SECRET not in response.text  # no detail of the failure
    deletes = [statement for kind, statement in log if kind == "sql" and statement.startswith("DELETE FROM")]
    assert deletes and deletes[0].startswith("DELETE FROM interview_turns")  # the turns went first, inside the transaction that was not committed
    assert any(s.startswith("DELETE FROM interview_sessions") for s in deletes) == (failing == "the final commit")

    monkeypatch.setattr(db, "execute", real_execute)
    monkeypatch.setattr(db, "commit", real_commit)
    db.rollback()  # what closing the session does at the end of a real request (`get_db`)
    assert state_of(db, target, sibling) == before and quota_rows(db) == quota_before  # the session, its turns and its feedback are all still there
    assert delete(api, world, target).status_code == 204  # and the same request works when the database does


# ── The M5 boundary ──


def test_deleting_a_live_session_only_removes_its_rows_and_the_agents_next_event_is_a_404(api, db, clock):
    world = build_world(db)
    live = seed(db, world, clock, S.LIVE, 600, turns=1)
    clock.advance(10)
    assert delete(api, world, live).status_code == 204  # nothing here tells an agent: the rows are simply gone
    turn = ingest.TurnEvent(seq=2, role="candidate", kind="answer", item_index=0, topic_id="c1", text="답변", coverage={"phase": "listening"})
    end = ingest.EndEvent(coverage={"phase": "aborted"})
    for send in (lambda: ingest.record_turn(db, live, turn, clock=clock), lambda: ingest.record_end(db, live, end, clock=clock)):
        with pytest.raises(AppError) as error:
            send()
        assert (error.value.status_code, error.value.code) == (404, "INTERVIEW_NOT_FOUND")  # what an M5 agent has to treat as "stop"
    assert state_of(db, live)[live] == (None, [])  # and the refused events wrote nothing
