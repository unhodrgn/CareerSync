"""`GET /api/interview-sessions/{session_id}` (M4 S4.4; docs/DECISIONS.md D67, D69): one session of the seeker, as the service shows it.

The route calls `interview_service.detail` and adds nothing, so these tests show that the HTTP layer keeps the service's contract: the same
shape as the `session` of the create response, the status derived from the deadlines (a session past its deadline reads `aborted` with its
reason), the topics with the engine's statuses and the masked turns in order, and nothing that is internal: no plan, coverage, feedback body,
CV text, rubric or weight. It is a read: no status is settled, no expired session is purged, and no statement but a SELECT is issued. What the
detail has in common with the other routes of the session (authentication, ownership, expiry, bad ids, the path) is in
test_interview_api_session_common.py. The database is the SQLite fixture."""
from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.models import InterviewSession, InterviewTurn
from app.models.interview import InterviewStatus as S
from app.schemas.application import AI_NOTICE

from .conftest import auth
from .interview_fixtures import SAMPLE_CV, build_world
from .test_interview_api_create import SESSION_KEYS
from .test_interview_api_history import keys_of
from .test_interview_api_session_common import DETAIL, URL, api, call, clock, no_store, no_wall_clock  # noqa: F401 (the fixtures)
from .test_interview_create import capture
from .test_interview_history_active import CASES, STALE_REASON, add, physical, quota_rows

TOPIC_KEYS = {"topic_id", "kind", "criterion_name", "importance", "status"}
TURN_KEYS = {"seq", "role", "kind", "text"}
VALID = {"consent_transcript": True, "consent_version": settings.INTERVIEW_CONSENT_VERSION}
INTERNAL_KEYS = {
    "plan", "coverage", "feedback", "feedback_method", "feedback_at", "feedback_attempts", "analysis", "masked_kinds", "method", "item_index",
    "cv_profile_id", "seeker_id", "consent_version", "consent_at", "limits", "plan_sha256", "prompt_version", "question", "rephrase", "rubric", "intent",
}
CV_MARKER, FEEDBACK_MARKER, ANALYSIS_MARKER, MASKED_MARKER = "CV-MARKER-경력", "FEEDBACK-MARKER", "ANALYSIS-MARKER", "MASKED-MARKER"


def get(api, world, session_id):
    return call(api, DETAIL, session_id, world.user)


def ok(response) -> dict:
    assert response.status_code == 200 and no_store(response) and response.headers["content-type"] == "application/json", response.text
    return response.json()


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def strings_in(value):
    """Every string anywhere in a JSON value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def create(api, world) -> dict:
    created = api.post(f"/api/jobs/{world.job_id}/interview-sessions", headers=auth(world.user), json=VALID)
    assert created.status_code == 201, created.text
    return created.json()["session"]


# ── The shape ──


def test_the_detail_of_a_created_session_is_the_session_the_create_route_returned(api, db, clock):
    world = build_world(db)
    session = create(api, world)
    body = ok(get(api, world, session["id"]))
    assert body == session  # the same fields and the same values
    assert set(body) == SESSION_KEYS and body["notice"] == AI_NOTICE and body["turns"] == []
    assert body["topics"] and all(set(topic) == TOPIC_KEYS for topic in body["topics"])
    assert {topic["status"] for topic in body["topics"]} == {"not_asked"} and {topic["importance"] for topic in body["topics"]} <= {"핵심", "중요", "일반", None}


def test_nothing_internal_leaves_in_the_detail(api, db, clock):
    world = build_world(db, masked_cv=SAMPLE_CV + "\n" + CV_MARKER)
    session = create(api, world)
    db.add(InterviewTurn(session_id=session["id"], seq=1, role="agent", kind="question", text="자기소개를 해 주세요.", method="rules",
                         analysis={"marker": ANALYSIS_MARKER}, masked_kinds={"marker": MASKED_MARKER}))
    row = db.get(InterviewSession, session["id"])
    row.feedback, row.feedback_method = {"strengths": [FEEDBACK_MARKER]}, "rules"
    db.commit()
    plan_texts = []
    for item in db.get(InterviewSession, session["id"]).plan["items"]:
        plan_texts += [item["question"], item["rephrase"], item["intent"], *item["answer_tips"], *(point["text"] for point in item["rubric"])]
    plan_texts = [text for text in plan_texts if text]
    assert plan_texts  # the stored plan has texts that must not come out

    response = get(api, world, session["id"])
    body = ok(response)
    blob = "\n".join(strings_in(body))
    for marker in (CV_MARKER, FEEDBACK_MARKER, ANALYSIS_MARKER, MASKED_MARKER):
        assert marker not in blob, marker
    assert [text for text in plan_texts if text in blob] == []  # no question, rephrasing, intent, tip or rubric point
    assert not INTERNAL_KEYS & keys_of(body) and not [key for key in keys_of(body) if "weight" in key.lower()]
    assert [set(turn) for turn in body["turns"]] == [TURN_KEYS] and body["feedback_status"] == "ready"  # the body of the feedback stays out


def test_the_turns_are_in_order_and_the_topics_carry_the_engines_statuses(api, db, clock):
    world = build_world(db)
    session_id = create(api, world)["id"]
    db.add(InterviewTurn(session_id=session_id, seq=2, role="candidate", kind="answer", text="저는 [이름]입니다."))
    db.add(InterviewTurn(session_id=session_id, seq=1, role="agent", kind="question", text="자기소개를 해 주세요."))
    db.commit()
    db.get(InterviewSession, session_id).coverage = {"phase": "listening", "status": {"c1": "partial", "c2": "asked"}, "levels": {}}
    db.commit()
    body = ok(get(api, world, session_id))
    assert [(t["seq"], t["role"], t["kind"], t["text"]) for t in body["turns"]] == [
        (1, "agent", "question", "자기소개를 해 주세요."), (2, "candidate", "answer", "저는 [이름]입니다."),
    ]
    assert {t["topic_id"]: t["status"] for t in body["topics"]} == {"c1": "partial", "c2": "asked", "c3": "not_asked", "behavioral": "not_asked"}


def test_a_feedback_is_reported_as_ready_and_otherwise_none(api, db, clock):
    world = build_world(db)
    ready = add(db, world, clock, S.COMPLETED, feedback={"topics": []}, feedback_method="rules")
    none = add(db, world, clock, S.COMPLETED)
    assert (ok(get(api, world, ready))["feedback_status"], ok(get(api, world, none))["feedback_status"]) == ("ready", "none")


def test_a_plan_that_cannot_be_read_and_a_session_still_being_planned_show_no_topics_and_no_turns(api, db, clock):
    world = build_world(db)
    unreadable = add(db, world, clock, S.COMPLETED, plan={"items": "not a list"})
    planning = add(db, world, clock, S.PLANNING, deadline=120)
    for session_id in (unreadable, planning):
        body = ok(get(api, world, session_id))
        assert body["topics"] == [] and body["turns"] == [], session_id
    assert ok(get(api, world, planning))["status"] == "planning"


# ── The derived state, and a read that writes nothing ──


@pytest.mark.parametrize("label, status, deadline, advance, active", CASES, ids=[case[0] for case in CASES])
def test_the_detail_shows_the_derived_state_and_issues_nothing_but_selects(api, db, clock, label, status, deadline, advance, active):
    world = build_world(db)
    session_id = add(db, world, clock, status, deadline=deadline)
    stored, quota_before = physical(db, session_id), quota_rows(db)
    start = clock.now
    clock.advance(advance)
    with capture(db) as log:
        body = ok(get(api, world, session_id))
    assert [entry for entry in log if entry[0] == "commit" or not entry[1].upper().startswith("SELECT")] == []  # a read: no write, no commit

    derived = active if active is not None else ("aborted" if status in S.ACTIVE else status)
    assert body["status"] == derived
    in_budget = derived == "live" and advance <= deadline
    assert (body["joinable"], body["accepting_turns"], body["end_grace_open"]) == (derived == "created", derived == "created" or in_budget, derived == "live" and not in_budget)
    if derived in S.ACTIVE:
        assert at(body["active_until"]) == start + timedelta(seconds=deadline) and body["end_reason"] is None
    else:
        assert body["active_until"] is None
    if active is None and status in S.ACTIVE:  # past its deadline: aborted for the reader, with the reason and the deadline it missed
        assert body["end_reason"] == STALE_REASON[status] and at(body["ended_at"]) == start + timedelta(seconds=deadline)
    assert physical(db, session_id) == stored and quota_rows(db) == quota_before  # the row still says what it said


def test_the_detail_deletes_nothing_not_even_an_expired_session(api, db, clock):
    world = build_world(db)
    expired = add(db, world, clock, S.COMPLETED, expires_in=-1)
    visible = add(db, world, clock, S.COMPLETED)
    ok(get(api, world, visible))
    db.expire_all()
    assert db.get(InterviewSession, expired) is not None  # only create, history and delete purge (D65)


def test_a_session_is_visible_until_the_instant_it_expires(api, db, clock):
    world = build_world(db)
    session_id = add(db, world, clock, S.COMPLETED, expires_in=100)
    clock.advance(99.999)
    assert ok(get(api, world, session_id))["id"] == session_id
    clock.advance(0.001)
    assert get(api, world, session_id).status_code == 404  # the other side of the boundary is in test_interview_api_session_common.py
