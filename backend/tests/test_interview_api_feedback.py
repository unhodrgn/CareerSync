"""`POST /api/interview-sessions/{session_id}/feedback`, Gate A: the foundation and the outcomes that need no model (M4 S4.5; docs/DECISIONS.md D63,
D64, D67).

The route calls `interview_feedback_service.ensure` and adds one thing to it: the `Retry-After` header of the busy 409 (D67 (6)), made with the
application's own AppError handler. These tests show that the HTTP layer keeps the service's contract: 200 for a final and a provisional report
alike, with `report` (exactly the stored or provisional `to_data()`), `final`, `limited`, `reason`, `generated_at` and `notice`, and nothing
internal; and, for the cases that never reach a model, the service's own outcome: a stored report before the consent is looked at, the 409
codes, the provisional report of a plan that does not match its digest, the rules report stored for rules mode, for a session with no
answers and for a session whose attempts are used up. In none of them is a model called (a spy counts) or a quota, an attempt or a lease
changed except where the service does. The model-backed outcomes (success, failure, quota, a lost lease) are in test_interview_api_feedback_model.py. The cases that every
route of a session shares (401, 403, 404, bad ids, 405, 307, no-store) are in test_interview_api_session_common.py. No real model: the
feedback model is the recording spy of the S3b tests. The database is the SQLite fixture."""
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from sqlalchemy import select

from ai.interview import FeedbackReport
from ai.interview import feedback as feedback_module
from app.core.config import settings
from app.core.errors import AppError
from app.main import app
from app.models import InterviewSession, InterviewTurn
from app.schemas.application import AI_NOTICE
from app.services import interview_feedback_service as fb
from app.services import interview_service as svc

from .interview_feedback_fixtures import (
    SpyLLM,
    agent_turn,
    askable_session,
    covered,
    feedback_used,
    finished_session,
    hand_session,
    install,
    plan_item,
    row,
)
from .interview_fixtures import Agent, build_world, new_session
from .test_interview_api_history import keys_of
from .test_interview_api_session_common import FEEDBACK, api, call, clock, no_store, no_wall_clock  # noqa: F401 (the fixtures)

TOP_KEYS = {"report", "final", "limited", "reason", "generated_at", "notice"}
REPORT_KEYS = {
    "method", "topics", "strengths", "gaps", "improvements", "practice_questions", "resources", "uncovered", "notes", "rules_sections", "rubric_notice",
}
NESTED_KEYS = {
    "topics": {"topic_id", "name", "importance", "status"}, "strengths": {"topic_id", "text", "quotes"}, "gaps": {"topic_id", "text"},
    "practice_questions": {"topic_id", "question"}, "resources": {"topic_id", "skill", "title", "url"},
    "uncovered": {"topic_id", "name", "importance", "reason"},
}
NOT_EXPOSED = {
    "prompt_version", "attempts_used", "attempts", "feedback_attempts", "feedback_lease_token", "feedback_lease_until", "lease", "token", "score", "rank",
    "ranking", "verdict", "hire", "weight", "cv", "cv_text", "prompt", "analysis", "plan", "coverage",
}


@pytest.fixture(autouse=True)
def roomy_sessions(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 20)  # a test makes several sessions of one seeker in a day


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return finished_session(db, world, clock)


def post(api, world, session_id):
    return call(api, FEEDBACK, session_id, world.user)


def ok(response) -> dict:
    assert response.status_code == 200 and no_store(response) and response.headers["content-type"] == "application/json", response.text
    assert "retry-after" not in response.headers  # only the busy 409 has it
    return response.json()


def refused(response, http, code, **extra) -> dict:
    """A business error: the status, the code, a message, the extra fields (checked by name), no-store, and no `Retry-After` (but for the busy one)."""
    assert response.status_code == http and no_store(response), response.text
    body = response.json()
    assert body["code"] == code and isinstance(body["message"], str) and body["message"] and "detail" not in body, body
    for key, value in extra.items():
        assert body[key] == value, (key, body)
    assert set(body) == {"code", "message", *extra}, body  # nothing else in an error
    assert ("retry-after" in response.headers) == (code == fb.BUSY)
    return body


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def unchanged(db, session_id, attempts=0):
    """The feedback columns of a session that nobody stored anything for."""
    r = row(db, session_id)
    assert (r.feedback, r.feedback_method, r.feedback_prompt_version, r.feedback_at) == (None, None, None, None)
    assert (r.feedback_lease_until, r.feedback_lease_token) == (None, None)
    assert r.feedback_attempts == attempts


def withdraw_consent(db, world):
    world.user.consent_ai_at = None  # DELETE /api/users/me/consent/ai
    db.commit()


def three_items():
    return [plan_item(1, "Java"), plan_item(2, "Spring Boot"), plan_item(3, "협업", kind="behavioral")]


def lease_held(db, session_id, seconds, clock):
    """A valid lease of another request: it ends `seconds` from now."""
    db.execute(
        InterviewSession.__table__.update().where(InterviewSession.id == session_id)
        .values(feedback_lease_until=clock() + timedelta(seconds=seconds), feedback_lease_token="b" * 32)
    )
    db.commit()


def allowed_urls() -> set[str]:
    """Every URL of the learning-resources allow-list."""
    found: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "url" and isinstance(item, str):
                    found.add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    with open(settings.LEARNING_RESOURCES_PATH, encoding="utf-8") as handle:
        walk(yaml.safe_load(handle))
    return found


# ── The rules report, stored: the fields, the evidence, the allow-list ──


def test_rules_mode_answers_200_with_the_stored_final_rules_report_and_nothing_internal(api, db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    body = ok(post(api, world, sid))
    assert set(body) == TOP_KEYS and body["notice"] == AI_NOTICE  # the notice is at the top, once
    assert (body["final"], body["limited"], body["reason"]) == (True, False, None)
    assert at(body["generated_at"]) == clock.now and set(body["report"]) == REPORT_KEYS and body["report"]["method"] == "rules"
    stored = row(db, sid)
    assert body["report"] == stored.feedback  # exactly what was stored: no field added, none dropped
    assert (stored.feedback_method, stored.feedback_prompt_version, stored.feedback_attempts) == ("rules", "v1", 0)
    assert (stored.feedback_lease_token, stored.feedback_lease_until) == (None, None) and feedback_used(db, world, clock) == 0
    assert not NOT_EXPOSED & keys_of(body) and not [key for key in keys_of(body) if "weight" in key.lower()]
    assert body["report"]["topics"] and all(set(topic) == NESTED_KEYS["topics"] for topic in body["report"]["topics"])
    assert {topic["importance"] for topic in body["report"]["topics"]} <= {"핵심", "중요", "일반", None}  # a label, never a weight


def test_the_evidence_the_links_and_every_nested_field_of_a_report_are_the_existing_ones(api, db, world, clock, monkeypatch):
    install(monkeypatch, None)
    session_id = askable_session(db, world, clock)  # a demonstrated topic with a candidate line that holds a stored quote
    report = ok(post(api, world, session_id))["report"]
    for section, expected in NESTED_KEYS.items():
        assert all(set(item) == expected for item in report[section]), section
    assert report["strengths"] and report["gaps"] and report["improvements"]
    candidate_lines = [t.text for t in db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == session_id, InterviewTurn.role == "candidate"))]
    for strength in report["strengths"]:
        assert strength["quotes"] and all(any(quote in line for line in candidate_lines) for quote in strength["quotes"])  # verbatim, from the candidate
    assert {link["url"] for link in report["resources"]} <= allowed_urls()  # only the allow-list
    assert report["rubric_notice"] == feedback_module.RUBRIC_NOTICE


# ── A stored report: before the consent, immutable ──


def test_a_stored_report_is_returned_before_the_consent_is_looked_at_and_a_repeat_is_identical(api, db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    first = ok(post(api, world, sid))
    withdraw_consent(db, world)
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    stored_row = row(db, sid)
    stored_at = stored_row.feedback_at
    for _ in range(3):
        clock.advance(500)
        again = ok(post(api, world, sid))
        assert again == first  # the same report, the same `generated_at`: nothing is made again
    assert spy.calls == [] and feedback_used(db, world, clock) == 0 and row(db, sid).feedback_at == stored_at
    assert row(db, sid).feedback == first["report"] and row(db, sid).feedback_attempts == 0


def test_a_user_who_never_gave_the_ai_consent_still_reads_a_stored_report(api, db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    first = ok(post(api, world, sid))
    world.user.consent_ai_at, world.user.consent_privacy_at, world.user.consent_version = None, None, None
    db.commit()
    assert ok(post(api, world, sid)) == first


def test_another_seekers_stored_report_is_never_returned(api, db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    other = build_world(db, email="two@interview.test")
    theirs = finished_session(db, other, clock)
    their_report = ok(post(api, other, theirs))
    response = post(api, world, theirs)
    assert response.status_code == 404 and no_store(response) and response.json()["code"] == "INTERVIEW_NOT_FOUND"
    assert their_report["generated_at"] not in response.text and "report" not in response.json()
    unchanged(db, sid)  # and mine was not touched


# ── No generation without the consent, nor before the interview is over ──


@pytest.mark.parametrize("mode", ["rules", "model"])
def test_a_new_generation_after_the_consent_was_withdrawn_is_a_409_in_both_modes(api, db, world, clock, mode, monkeypatch):
    fresh = finished_session(db, world, clock)
    withdraw_consent(db, world)
    spy = SpyLLM(db)
    install(monkeypatch, spy if mode == "model" else None)
    body = refused(post(api, world, fresh), 409, fb.CONSENT_REQUIRED)
    assert set(body) == {"code", "message"}
    unchanged(db, fresh)
    assert spy.calls == [] and feedback_used(db, world, clock) == 0


def test_withdrawn_consent_blocks_a_provisional_report_too(api, db, world, clock, monkeypatch):
    install(monkeypatch, None)
    odd = hand_session(db, world, clock, three_items(), sha256="0" * 64)  # would be provisional: the digest does not match
    withdraw_consent(db, world)
    refused(post(api, world, odd), 409, fb.CONSENT_REQUIRED)
    unchanged(db, odd)


def test_an_interview_that_is_not_over_has_no_feedback_yet(api, db, world, clock, monkeypatch):
    created = new_session(db, world, clock)
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    refused(post(api, world, created), 409, fb.NOT_ENDED, status="created")
    install(monkeypatch, None)
    Agent(db, created, clock).start()
    install(monkeypatch, spy)
    refused(post(api, world, created), 409, fb.NOT_ENDED, status="live")
    assert spy.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, created)


def test_the_consent_is_checked_before_whether_the_interview_is_over(api, db, world, clock, monkeypatch):
    created = new_session(db, world, clock)
    install(monkeypatch, None)
    withdraw_consent(db, world)
    refused(post(api, world, created), 409, fb.CONSENT_REQUIRED)  # not INTERVIEW_NOT_ENDED: the service's order
    unchanged(db, created)


# ── The plan ──


@pytest.mark.parametrize(
    "plan_data",
    [{"items": []}, {"items": [{"topic_id": "c1"}]}, {"items": "oops"}, {"nothing": 1}, None],
    ids=["no items", "unreadable item", "items is not a list", "no items key", "no plan"],
)
def test_no_safe_view_of_the_plan_is_the_existing_409_and_no_model_is_called(api, db, world, clock, monkeypatch, plan_data):
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    broken = hand_session(db, world, clock, [], plan_data=plan_data)
    body = refused(post(api, world, broken), 409, fb.PLAN_INVALID)
    assert set(body) == {"code", "message"} and spy.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, broken)


@pytest.mark.parametrize("sha256", ["0" * 64, None], ids=["digest does not match", "no digest"])
def test_a_plan_that_does_not_match_its_digest_gives_the_existing_provisional_rules_report(api, db, world, clock, monkeypatch, sha256):
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    items = three_items()
    odd = hand_session(db, world, clock, items, sha256=sha256, coverage=covered(items, {}))
    body = ok(post(api, world, odd))
    assert (body["final"], body["limited"], body["reason"], body["generated_at"]) == (False, False, fb.REASON_PLAN_INVALID, None)
    assert set(body) == TOP_KEYS and body["report"]["method"] == "rules" and set(body["report"]) == REPORT_KEYS and body["notice"] == AI_NOTICE
    again = ok(post(api, world, odd))
    assert again["report"] == body["report"] and again["final"] is False  # made again each time: never stored
    assert spy.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, odd)


# ── Rules mode, no answers, attempts used up: the rules report is stored ──


def test_a_session_without_answers_gets_the_final_rules_report_with_no_model_and_no_quota(api, db, world, clock, monkeypatch):
    empty = new_session(db, world, clock)  # (planned in rules mode: the model is installed afterwards)
    svc.end(db, world.user, empty, clock=clock)  # ended before it started: aborted, a plan, no turns
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    body = ok(post(api, world, empty))
    assert (body["final"], body["limited"], body["reason"]) == (True, False, None) and body["report"]["method"] == "rules"
    assert feedback_module.NOTE_NO_ANSWERS in body["report"]["notes"]
    assert spy.calls == [] and feedback_used(db, world, clock) == 0
    stored = row(db, empty)
    assert stored.feedback == body["report"] and stored.feedback_attempts == 0 and stored.feedback_lease_token is None


def test_attempts_that_are_used_up_with_a_dead_lease_give_the_final_rules_report_and_ask_no_model(api, db, world, clock, sid, monkeypatch):
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    db.execute(
        InterviewSession.__table__.update().where(InterviewSession.id == sid)
        .values(feedback_attempts=3, feedback_lease_until=clock() - timedelta(seconds=1), feedback_lease_token="a" * 32)
    )
    db.commit()
    body = ok(post(api, world, sid))
    assert (body["final"], body["reason"], body["report"]["method"]) == (True, None, "rules")
    assert spy.calls == [] and feedback_used(db, world, clock) == 0
    assert row(db, sid).feedback_lease_token is None and row(db, sid).feedback_attempts == 3  # no fourth attempt, and no refund


# ── The busy lease and its Retry-After ──


@pytest.mark.parametrize("seconds", [120, 45, 1])
def test_a_lease_that_another_request_holds_gives_the_409_with_a_retry_after_equal_to_the_body(api, db, world, clock, sid, monkeypatch, seconds):
    spy = SpyLLM(db)
    install(monkeypatch, spy)
    lease_held(db, sid, seconds, clock)
    response = post(api, world, sid)
    body = refused(response, 409, fb.BUSY, retry_after_seconds=seconds)
    assert response.headers["retry-after"] == str(seconds) == str(body["retry_after_seconds"])
    assert response.headers.get_list("retry-after") == [str(seconds)] and response.headers["content-type"] == "application/json"
    assert spy.calls == [] and feedback_used(db, world, clock) == 0  # this request took nothing
    stored = row(db, sid)
    assert (stored.feedback, stored.feedback_attempts, stored.feedback_lease_token) == (None, 0, "b" * 32)  # and did not touch the other's lease


def test_the_busy_body_is_the_one_the_application_handler_makes_and_only_the_header_is_added(api, db, world, clock, sid, monkeypatch):
    install(monkeypatch, SpyLLM(db))
    lease_held(db, sid, 120, clock)
    response = post(api, world, sid)
    expected = app.exception_handlers[AppError](None, AppError(409, fb.BUSY, response.json()["message"], retry_after_seconds=120))
    assert (response.status_code, response.content) == (expected.status_code, expected.body)  # the same status and the same bytes
    assert set(response.headers) - set(expected.headers) == {"retry-after", "cache-control"}  # the header, and the no-store of the middleware


def test_the_route_uses_the_application_error_handler_and_not_a_copy_of_it(api, db, world, clock, sid, monkeypatch):
    from fastapi.responses import JSONResponse

    install(monkeypatch, SpyLLM(db))
    lease_held(db, sid, 30, clock)
    monkeypatch.setitem(app.exception_handlers, AppError, lambda request, exc: JSONResponse({"made_by": "the handler"}, status_code=exc.status_code))
    response = post(api, world, sid)
    assert response.json() == {"made_by": "the handler"} and response.headers["retry-after"] == "30"


def test_retry_after_is_for_the_busy_409_only(api, db, world, clock, sid, monkeypatch):
    for error in (
        AppError(409, fb.CONSENT_REQUIRED, "consent"), AppError(409, fb.NOT_ENDED, "not over", status="live"), AppError(409, fb.PLAN_INVALID, "plan"),
        AppError(404, "INTERVIEW_NOT_FOUND", "gone"), AppError(403, "SEEKER_ONLY", "seekers"), AppError(409, "SOMETHING_ELSE", "x", retry_after_seconds=9),
    ):
        def fail(db, user, session_id, *, clock=None, error=error):
            raise error

        monkeypatch.setattr(fb, "ensure", fail)
        response = post(api, world, sid)
        assert response.status_code == error.status_code and no_store(response) and "retry-after" not in response.headers, error.code
        assert response.json() == {"code": error.code, "message": error.message, **error.extra}  # the handler's body, untouched
    monkeypatch.setattr(fb, "ensure", lambda *args, **kwargs: (_ for _ in ()).throw(AppError(409, fb.BUSY, "busy", retry_after_seconds=7)))
    busy = post(api, world, sid)
    assert busy.status_code == 409 and busy.headers["retry-after"] == "7" and busy.json() == {"code": fb.BUSY, "message": "busy", "retry_after_seconds": 7}


def test_an_unexpected_error_is_a_sanitized_500_with_no_store(api, db, world, clock, sid, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("SECRET-MARKER-답변-내용")

    monkeypatch.setattr(fb, "ensure", boom)
    response = post(api, world, sid)
    assert response.status_code == 500 and no_store(response) and "SECRET-MARKER" not in response.text and "retry-after" not in response.headers


# ── The mapping of every result the service can give (the flows themselves are Gate B) ──


def result(**overrides):
    values = dict(
        data=FeedbackReport("rules", (), (), (), (), (), (), ()).to_data(), final=False, limited=False, reason=None, method="rules", prompt_version="v1",
        generated_at=None, attempts_used=2,
    )
    values.update(overrides)
    return fb.FeedbackResult(**values)


@pytest.mark.parametrize(
    "made, expected",
    [
        (dict(final=True, generated_at=datetime(2026, 11, 16, 3, 0, tzinfo=UTC), method="llm:spy-llm"), (True, False, None, "2026-11-16T03:00:00Z")),
        (dict(final=False, limited=True, reason=fb.REASON_QUOTA), (False, True, fb.REASON_QUOTA, None)),
        (dict(final=False, reason=fb.REASON_MODEL_FAILED), (False, False, fb.REASON_MODEL_FAILED, None)),
        (dict(final=False, reason=fb.REASON_PLAN_INVALID), (False, False, fb.REASON_PLAN_INVALID, None)),
        (dict(final=False, reason=fb.REASON_LEASE_LOST), (False, False, fb.REASON_LEASE_LOST, None)),
    ],
    ids=["stored by a model", "quota used up", "model failed", "plan invalid", "lease lost"],
)
def test_every_kind_of_result_is_a_200_with_the_same_fields_and_nothing_of_the_service_internals(api, db, world, clock, sid, monkeypatch, made, expected):
    seen = []

    def ensure(db_, user, session_id, *, clock=None):
        seen.append((session_id, clock))
        return result(**made)

    monkeypatch.setattr(fb, "ensure", ensure)
    monkeypatch.setattr(fb, "stored", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("the route must not call `stored`")))
    body = ok(post(api, world, sid))
    assert set(body) == TOP_KEYS and body["notice"] == AI_NOTICE
    assert (body["final"], body["limited"], body["reason"], body["generated_at"]) == expected
    assert body["report"] == result().data  # the report as the service made it
    assert not NOT_EXPOSED & keys_of(body) and "method" not in body  # no `prompt_version`, `attempts_used`, or a second `method`
    assert seen == [(sid, seen[0][1])] and seen[0][1] is not None  # the path id, and the injected clock
