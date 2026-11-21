"""`POST /api/jobs/{job_id}/interview-sessions` (M4 S4.2; docs/DECISIONS.md D58, D65, D67): the cases that can happen to this route.

The route calls `interview_service.create_session` and adds nothing, so these tests show that the HTTP layer keeps the service's contract:
the status codes, the error codes and their extra fields, the response shape, the strict reading of the consent fields, and that nothing
that a refused request could have taken (a session, a reservation) is left behind. Every status asserted here is asserted together with
`Cache-Control: no-store`. The clock reaches the service through the overridable dependency `get_clock`: each test sets it, and a tripwire
makes any read of the real clock by the time and quota services fail, so no test depends on the date.

No model is called but the fake one of `interview_fixtures`; the database is the SQLite fixture."""
import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.v1.interview_sessions import get_clock
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.schemas.application import AI_NOTICE
from app.services import ai_runtime, interview_service, interview_time
from app.services import interview_quota_service as quota_service

from .conftest import auth
from .interview_fixtures import KEPT_LINES, REMOVED_LINES, SAMPLE_CV, Clock, PlanLLM, build_world

SECRET = "SECRET-MARKER-답변-내용"
VERSION = settings.INTERVIEW_CONSENT_VERSION
VALID = {"consent_transcript": True, "consent_version": VERSION}
SESSION_KEYS = {
    "id", "job_id", "job_title", "status", "end_reason", "plan_method", "max_seconds", "created_at", "started_at", "ended_at", "active_until",
    "expires_at", "joinable", "accepting_turns", "end_grace_open", "feedback_status", "topics", "turns", "notice",
}
NUL = "\x00"


class _NoWallClock:
    @staticmethod
    def now(*args, **kwargs):
        raise AssertionError("the wall clock was read: the route must use the clock it was given")


@pytest.fixture(autouse=True)
def no_wall_clock(monkeypatch):
    monkeypatch.setattr(interview_time, "datetime", _NoWallClock)
    monkeypatch.setattr(quota_service, "datetime", _NoWallClock)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def api(db, clock):
    """A client whose requests use the test database and the test clock, and whose unexpected errors come back as the 500 response."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def create(api, world, job_id=None, body=VALID, **kwargs):
    """POST the create request as `world`'s user, for `world`'s job unless another is named."""
    return api.post(f"/api/jobs/{world.job_id if job_id is None else job_id}/interview-sessions", headers=auth(world.user), json=body, **kwargs)


def url_of(world, job_id=None):
    return f"/api/jobs/{world.job_id if job_id is None else job_id}/interview-sessions"


def stored(db):
    """(sessions, {quota kind: used}) as the database has them now."""
    db.rollback()
    db.expire_all()
    return db.query(InterviewSession).count(), {row.kind: row.used for row in db.query(InterviewQuota)}


def no_store(response) -> bool:
    return response.headers.get_list("cache-control") == ["no-store"]


def refused(response, http, code, **extra):
    """A business error: the HTTP status, the code, the message, and the extra fields the service gave (checked by name)."""
    assert response.status_code == http and no_store(response), response.text
    body = response.json()
    assert body["code"] == code and isinstance(body["message"], str) and body["message"], body
    for key, value in extra.items():
        assert body[key] == value, (key, body)
    assert "detail" not in body  # a business error, not a validation error
    return body


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


# ── 201: the session is created ──


def test_a_seeker_creates_a_session_and_gets_201_with_the_session_and_limited(api, db, clock):
    world = build_world(db)
    response = create(api, world)
    assert response.status_code == 201 and no_store(response) and response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"session", "limited"} and body["limited"] is False
    session = body["session"]
    assert set(session) == SESSION_KEYS
    assert (session["status"], session["joinable"], session["accepting_turns"], session["end_grace_open"]) == ("created", True, True, False)
    assert (session["job_id"], session["job_title"], session["plan_method"], session["feedback_status"]) == (world.job_id, "Backend Engineer", "rules", "none")
    assert (session["max_seconds"], session["end_reason"], session["started_at"], session["ended_at"], session["turns"]) == (settings.INTERVIEW_MAX_SECONDS, None, None, None, [])
    assert session["notice"] == AI_NOTICE
    assert session["topics"] and all(set(t) == {"topic_id", "kind", "criterion_name", "importance", "status"} for t in session["topics"])
    assert {t["status"] for t in session["topics"]} == {"not_asked"} and {t["importance"] for t in session["topics"]} <= {"핵심", "중요", "일반", None}


def test_the_deadlines_come_from_the_clock_the_dependency_gave(api, db, clock):
    world = build_world(db)
    session = create(api, world).json()["session"]
    assert at(session["created_at"]) == clock.now
    assert at(session["active_until"]) == clock.now + timedelta(seconds=settings.INTERVIEW_JOIN_SECONDS)
    assert at(session["expires_at"]) == clock.now + timedelta(days=settings.INTERVIEW_RETENTION_DAYS)
    assert all(at(session[key]).tzinfo is not None for key in ("created_at", "active_until", "expires_at"))  # aware UTC


def test_creating_stores_one_planned_session_with_its_consent_and_takes_one_session_reservation(api, db, clock):
    world = build_world(db)
    session_id = create(api, world).json()["session"]["id"]
    sessions, used = stored(db)
    assert (sessions, used) == (1, {"session": 1})  # rules mode: no planning-model reservation
    row = db.get(InterviewSession, session_id)
    assert (row.status, row.seeker_id, row.consent_version, row.plan_method, row.feedback) == ("created", world.user.id, VERSION, "rules", None)
    assert row.plan and row.plan_sha256 and row.consent_at.replace(tzinfo=UTC) == clock.now
    assert db.query(InterviewTurn).count() == 0


def test_the_response_shows_no_weight_no_cv_line_and_no_personal_data(api, db):
    world = build_world(db)
    response = create(api, world)
    text = response.text
    for secret in (world.user.email, *REMOVED_LINES, *KEPT_LINES):
        assert secret not in text, secret

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    assert not [k for k in keys(response.json()) if "weight" in k.lower()]  # importance labels only (AI rule 9)


def test_with_a_model_configured_the_plan_is_asked_once_outside_any_transaction_and_both_reservations_are_taken(api, db, monkeypatch):
    world = build_world(db)
    llm = PlanLLM(db)
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    body = create(api, world).json()
    assert body["limited"] is False and body["session"]["plan_method"] == "llm:fake-llm"
    assert len(llm.calls) == 1 and llm.in_transaction == [False]  # the service's guarantee, through the route
    assert stored(db)[1] == {"session": 1, "plan_model": 1}


def test_when_only_the_planning_model_quota_is_gone_it_is_201_with_limited_true_and_the_template(api, db, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_PLAN_MODEL_CALLS", 0)
    world = build_world(db)
    llm = PlanLLM(db)
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    response = create(api, world)
    assert response.status_code == 201 and no_store(response)
    body = response.json()
    assert body["limited"] is True and body["session"]["plan_method"] == "rules" and llm.calls == []
    assert stored(db)[1].get("plan_model", 0) == 0 and stored(db)[1]["session"] == 1


def test_the_default_clock_is_the_real_one():
    assert get_clock() is interview_time.utcnow


# ── 401 and 403 ──


def test_no_token_is_401_and_nothing_is_taken(api, db):
    world = build_world(db)
    response = api.post(url_of(world), json=VALID)
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer" and no_store(response)
    assert stored(db) == (0, {})


@pytest.mark.parametrize("headers", [{"Authorization": "Bearer not-a-token"}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}])
def test_a_malformed_token_is_401(api, db, headers):
    world = build_world(db)
    response = api.post(url_of(world), headers=headers, json=VALID)
    assert response.status_code == 401 and no_store(response) and stored(db) == (0, {})


def test_a_company_user_is_403_seeker_only_before_the_job_is_looked_up(api, db):
    world = build_world(db)
    company = build_world(db, email="hr@interview.test", role="company")
    for job_id in (world.job_id, 999999):  # an unknown job gives the same 403: the role is checked first
        refused(create(api, company, job_id), 403, "SEEKER_ONLY")
    assert stored(db) == (0, {})


# ── 404 ──


@pytest.mark.parametrize("job_id", [999999, 0, -5])
def test_an_unknown_job_is_404(api, db, job_id):
    world = build_world(db)
    refused(create(api, world, job_id), 404, "JOB_NOT_FOUND")
    assert stored(db) == (0, {})


@pytest.mark.parametrize("options", [{"status": "draft"}, {"deadline": date(2000, 1, 1)}], ids=["not published", "past its deadline"])
def test_a_job_that_is_not_open_is_404(api, db, options):
    world = build_world(db, **options)
    refused(create(api, world), 404, "JOB_NOT_FOUND")
    assert stored(db) == (0, {})


# ── 409 ──


def test_without_the_ai_consent_it_is_409(api, db):
    world = build_world(db, ai_consent=False)
    refused(create(api, world), 409, "AI_CONSENT_REQUIRED")
    assert stored(db) == (0, {})


def test_after_the_ai_consent_is_withdrawn_it_is_409(api, db):
    world = build_world(db)
    world.user.consent_ai_at = None  # DELETE /api/users/me/consent/ai
    db.commit()
    refused(create(api, world), 409, "AI_CONSENT_REQUIRED")
    assert stored(db) == (0, {})


def test_without_a_confirmed_cv_it_is_409(api, db):
    world = build_world(db, confirmed=False)
    refused(create(api, world), 409, "CV_NOT_CONFIRMED")
    assert stored(db) == (0, {})


MISSING_OR_NOT_TRUE = {
    "no body fields": {},
    "no consent": {"consent_version": VERSION},
    "false": {"consent_transcript": False, "consent_version": VERSION},
    "the string true": {"consent_transcript": "true", "consent_version": VERSION},
    "the number 1": {"consent_transcript": 1, "consent_version": VERSION},
    "null": {"consent_transcript": None, "consent_version": VERSION},
    "a list": {"consent_transcript": [True], "consent_version": VERSION},
    "an object": {"consent_transcript": {"yes": True}, "consent_version": VERSION},
}


@pytest.mark.parametrize("body", MISSING_OR_NOT_TRUE.values(), ids=MISSING_OR_NOT_TRUE.keys())
def test_a_consent_that_is_missing_or_not_exactly_true_is_the_services_409_and_not_a_422(api, db, body):
    world = build_world(db)
    refused(create(api, world, body=body), 409, "INTERVIEW_CONSENT_REQUIRED", current_version=VERSION)
    assert stored(db) == (0, {})  # checked before anything is read or reserved


WRONG_VERSION = {
    "an old version": "2026-11-15",
    "a newer one": "2026-11-17",
    "empty": "",
    "a trailing space": VERSION + " ",
    "null": None,
    "a number": 20261116,
    "a list": ["2026-11-16"],
    "true": True,
}


@pytest.mark.parametrize("version", WRONG_VERSION.values(), ids=WRONG_VERSION.keys())
def test_a_consent_version_that_is_not_exactly_the_current_one_is_409_outdated(api, db, version):
    world = build_world(db)
    refused(create(api, world, body={"consent_transcript": True, "consent_version": version}), 409, "INTERVIEW_CONSENT_OUTDATED", current_version=VERSION)
    assert stored(db) == (0, {})


def test_a_second_create_while_a_session_is_active_is_409_with_its_id_and_takes_nothing(api, db):
    world = build_world(db)
    first = create(api, world).json()["session"]
    before = stored(db)
    body = refused(create(api, world), 409, "INTERVIEW_SESSION_ACTIVE", session_id=first["id"], status="created")
    assert set(body) == {"code", "message", "session_id", "status"}
    assert stored(db) == before == (1, {"session": 1})  # the second request's session and reservation were rolled back with it


def test_a_planning_lease_that_ran_out_is_409_planning_expired_with_the_session_id_and_the_reservations_stay_spent(api, db, clock, monkeypatch):
    world = build_world(db)
    llm = PlanLLM(db, on_call=lambda _llm: clock.advance(settings.INTERVIEW_PLAN_LEASE_SECONDS + 1))
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    body = refused(create(api, world), 409, "INTERVIEW_PLANNING_EXPIRED")
    sessions, used = stored(db)
    assert sessions == 1 and used == {"session": 1, "plan_model": 1}  # nothing is given back
    assert db.get(InterviewSession, body["session_id"]).status == "planning"  # not brought back; the lease and `settle` end it


# ── 422 from the service ──


def test_a_job_without_usable_criteria_is_422_not_available_and_nothing_is_reserved(api, db):
    world = build_world(db, criteria=())
    body = refused(create(api, world), 422, "INTERVIEW_NOT_AVAILABLE")
    assert "detail" not in body and stored(db) == (0, {})


def test_a_cv_the_plan_refuses_is_422_not_available_and_the_session_is_closed(api, db, monkeypatch):
    world = build_world(db)
    # U+0000 in the cleaned CV: refused before any model. PostgreSQL cannot store a NUL in `cv_documents.masked_text` (the INSERT of the fixture
    # fails there), so the text is patched in at the one place the service reads the stored CV, and this runs the same on SQLite and PostgreSQL.
    monkeypatch.setattr(interview_service, "_read_stored_cv", lambda _db, _cv_document_id: SAMPLE_CV.replace("Java", "Ja" + NUL + "va", 1))
    llm = PlanLLM(db)
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    refused(create(api, world), 422, "INTERVIEW_NOT_AVAILABLE")
    sessions, used = stored(db)
    row = db.query(InterviewSession).one()
    assert (sessions, row.status, row.end_reason, row.plan) == (1, "aborted", "plan_unavailable", None) and llm.calls == []
    assert used["session"] == 1  # the reservation was taken before the plan was tried, and is not given back


# ── 429 ──


def test_the_fourth_session_of_a_day_is_429_with_the_quota_the_limit_and_the_reset_time(api, db, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 1)
    world = build_world(db)
    first = create(api, world).json()["session"]
    interview_service.end(db, world.user, first["id"], clock=clock)  # a new session needs the first one to be over
    body = refused(create(api, world), 429, "INTERVIEW_DAILY_LIMIT", quota="sessions", limit=1)
    local = clock.now.astimezone(quota_service.KST)
    assert body["resets_at"] == (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    assert set(body) == {"code", "message", "quota", "limit", "resets_at"}
    assert stored(db) == (1, {"session": 1})  # the refused request left no session and no extra reservation


# ── 422 from validation: nothing submitted is echoed ──

VALIDATION_CASES = {
    "an id that is not a number": dict(url="/api/jobs/SECRETPATH/interview-sessions", json=VALID),
    "no body": dict(url=None),
    "a body that is not JSON": dict(url=None, content=b"{" + SECRET.encode() + b"}", headers={"content-type": "application/json"}),
    "a body that is not an object": dict(url=None, json=[SECRET]),
    "a body sent as text": dict(url=None, content=SECRET.encode(), headers={"content-type": "text/plain"}),
    "an unknown field": dict(url=None, json={**VALID, SECRET: SECRET}),
}


@pytest.mark.parametrize("name", list(VALIDATION_CASES), ids=list(VALIDATION_CASES))
def test_a_malformed_request_is_a_422_with_no_submitted_value_in_it_or_in_the_logs(api, db, caplog, name):
    world = build_world(db)
    case = dict(VALIDATION_CASES[name])
    url = case.pop("url") or url_of(world)
    headers = {"Authorization": f"Bearer {auth(world.user)['Authorization'][7:]}", **case.pop("headers", {})}
    caplog.set_level(logging.DEBUG)
    response = api.post(url, headers=headers, **case)
    assert response.status_code == 422 and no_store(response)
    body = response.json()
    assert set(body) == {"detail"} and body["detail"], body  # FastAPI's shape, not the service's {code, message}
    for error in body["detail"]:
        assert set(error) == {"type", "loc", "msg"}  # no `input`, no `ctx`, no `url`
    # The logs of the server side: the test client logs the URL it requested, as a real server's access log prints the path (an id).
    server_logs = " ".join(r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore", "asyncio")))
    shown = response.text + str(dict(response.headers)) + server_logs
    assert SECRET not in shown and "SECRETPATH" not in shown
    assert stored(db) == (0, {})  # a malformed request takes nothing


def test_an_unknown_field_is_named_by_its_kind_and_not_by_its_name(api, db):
    world = build_world(db)
    response = api.post(url_of(world), headers=auth(world.user), json={**VALID, "consent": "yes"})
    (error,) = response.json()["detail"]
    assert (response.status_code, error["type"], error["loc"], error["msg"]) == (422, "extra_forbidden", ["body"], "Extra inputs are not permitted")


def test_a_bad_id_keeps_its_location_so_the_client_can_fix_it(api, db):
    world = build_world(db)
    response = api.post("/api/jobs/abc/interview-sessions", headers=auth(world.user), json=VALID)
    (error,) = response.json()["detail"]
    assert (response.status_code, error["type"], error["loc"]) == (422, "int_parsing", ["path", "job_id"])


def test_no_consent_fields_at_all_is_not_a_validation_error(api, db):
    world = build_world(db)
    assert create(api, world, body={}).status_code == 409  # `{}` is a valid body: the service says the consent is missing


# ── Methods, the trailing slash, an unexpected error ──


@pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
def test_other_methods_are_405(api, db, method):
    world = build_world(db)
    response = getattr(api, method)(url_of(world), headers=auth(world.user))
    assert response.status_code == 405 and "POST" in response.headers["allow"] and no_store(response)


def test_the_trailing_slash_redirects_before_any_check(api, db):
    world = build_world(db)
    response = api.post(url_of(world) + "/", json=VALID, follow_redirects=False)  # no token: the router redirects before a dependency runs
    assert response.status_code == 307 and response.headers["location"].endswith(url_of(world)) and no_store(response)
    assert stored(db) == (0, {})


def test_an_unexpected_service_failure_is_a_plain_500_with_the_header_and_nothing_of_the_error(api, db, monkeypatch):
    world = build_world(db)

    def broken(*args, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(interview_service, "create_session", broken)
    response = create(api, world)
    assert (response.status_code, response.text) == (500, "Internal Server Error") and no_store(response)
    assert SECRET not in response.text and SECRET not in str(dict(response.headers))
    assert stored(db) == (0, {})
