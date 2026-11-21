"""`GET /api/interview-sessions` (M4 S4.3; docs/DECISIONS.md D67, D68): the cases that can happen to this route.

The route calls `interview_service.history` and adds nothing, so these tests show that the HTTP layer keeps the service's contract: the page
(`items`, `next_before_id`), the one active session (`active`, always present, null when there is none, independent of `job_id`, `limit` and
`before_id`), the plain optional integer parameters, and that a read changes nothing. Every status asserted here is asserted together with
`Cache-Control: no-store`. The clock reaches the service through the overridable dependency `get_clock`, and a tripwire makes any read of the
real clock by the time and quota services fail. The service-level cases of `active`, and the table of lifecycle states used here, are in
test_interview_history_active.py. The route is read-only and uses no quota and no model; the database is the SQLite fixture."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.v1.interview_sessions import get_clock
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewSession, InterviewTurn
from app.models.interview import InterviewStatus as S
from app.schemas.application import AI_NOTICE
from app.services import ai_runtime, interview_service, interview_time
from app.services import interview_quota_service as quota_service

from .conftest import auth
from .interview_fixtures import Clock, build_world
from .test_interview_history_active import CASES, STALE_REASON, add, new_job, physical, quota_rows

URL = "/api/interview-sessions"
SECRET = "SECRET-MARKER-답변-내용"
PAGE_KEYS = {"items", "next_before_id", "active", "notice"}
ITEM_KEYS = {"id", "job_id", "job_title", "status", "end_reason", "created_at", "ended_at", "active_until", "expires_at", "joinable", "feedback_status"}
VALID = {"consent_transcript": True, "consent_version": settings.INTERVIEW_CONSENT_VERSION}


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


def get(api, world, **params):
    """GET the history as `world`'s user."""
    return api.get(URL, params=params, headers=auth(world.user))


def no_store(response) -> bool:
    return response.headers.get_list("cache-control") == ["no-store"]


def ok(response) -> dict:
    assert response.status_code == 200 and no_store(response) and response.headers["content-type"] == "application/json", response.text
    return response.json()


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def keys_of(value) -> set[str]:
    """Every key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


# ── Who may ask ──


def test_no_token_is_401(api):
    response = api.get(URL)
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer" and no_store(response)


@pytest.mark.parametrize("headers", [{"Authorization": "Bearer not-a-token"}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}])
def test_a_malformed_token_is_401(api, headers):
    response = api.get(URL, headers=headers)
    assert response.status_code == 401 and no_store(response)


def test_a_company_user_gets_403_seeker_only_and_nothing_else(api, db):
    company = build_world(db, email="c@interview.test", role="company")
    response = get(api, company)
    assert response.status_code == 403 and no_store(response)
    body = response.json()
    assert body["code"] == "SEEKER_ONLY" and isinstance(body["message"], str) and body["message"]
    assert not {"items", "active", "next_before_id"} & set(body) and "detail" not in body


# ── The page ──


def test_a_seeker_with_no_session_gets_an_empty_page_with_an_explicit_null_active(api, db):
    body = ok(get(api, build_world(db)))
    assert body == {"items": [], "next_before_id": None, "active": None, "notice": AI_NOTICE}


def test_the_page_and_its_items_have_exactly_the_documented_fields_and_nothing_internal(api, db, clock):
    world = build_world(db)
    session_id = add(
        db, world, clock, S.COMPLETED,
        plan={"questions": [SECRET]}, coverage={"note": SECRET}, feedback={"strengths": [SECRET]}, feedback_method="rules", plan_method="rules",
    )
    db.add(InterviewTurn(session_id=session_id, seq=1, role="candidate", kind="answer", item_index=0, text=SECRET))
    add(db, world, clock, S.CREATED, deadline=300)
    db.commit()
    response = get(api, world)
    body = ok(response)
    assert set(body) == PAGE_KEYS and body["notice"] == AI_NOTICE
    assert len(body["items"]) == 2 and all(set(item) == ITEM_KEYS for item in body["items"]) and set(body["active"]) == ITEM_KEYS
    assert SECRET not in response.text  # no plan, coverage, feedback or transcript text
    assert not [key for key in keys_of(body) if "weight" in key.lower()]
    assert "notice" not in body["items"][0] and "notice" not in body["active"]  # one notice for the page
    done = next(item for item in body["items"] if item["id"] == session_id)
    assert (done["job_title"], done["status"], done["feedback_status"], done["joinable"], done["end_reason"]) == ("Backend Engineer", "completed", "ready", False, None)


def test_the_items_are_newest_first_and_the_cursor_walks_the_whole_history(api, db, clock):
    world = build_world(db)
    ids = [add(db, world, clock, S.COMPLETED) for _ in range(5)]
    assert [item["id"] for item in ok(get(api, world))["items"]] == ids[::-1]
    seen, before = [], None
    for _ in range(10):
        body = ok(get(api, world, limit=2, **({} if before is None else {"before_id": before})))
        seen += [item["id"] for item in body["items"]]
        before = body["next_before_id"]
        if before is None:
            break
    assert seen == ids[::-1] and before is None


def test_the_page_size_defaults_and_is_clamped(api, db, clock):
    world = build_world(db)
    for _ in range(settings.INTERVIEW_HISTORY_MAX_LIMIT + 1):
        add(db, world, clock, S.COMPLETED)

    def size(**params) -> int:
        return len(ok(get(api, world, **params))["items"])

    assert size() == settings.INTERVIEW_HISTORY_DEFAULT_LIMIT
    assert (size(limit=1), size(limit=0), size(limit=-5)) == (1, 1, 1)
    assert size(limit=10_000) == settings.INTERVIEW_HISTORY_MAX_LIMIT
    full = ok(get(api, world, limit=10_000))
    assert full["next_before_id"] == full["items"][-1]["id"]  # more pages follow


def test_the_job_filter_narrows_the_items_and_an_unknown_or_foreign_job_is_an_empty_page(api, db, clock):
    world, other_world = build_world(db), build_world(db, email="two@interview.test")
    second = new_job(db, world)
    first_job_session = add(db, world, clock, S.COMPLETED)
    second_job_session = add(db, world, clock, S.COMPLETED, job_id=second)
    add(db, other_world, clock, S.COMPLETED)

    def ids(**params) -> list[int]:
        return [item["id"] for item in ok(get(api, world, **params))["items"]]

    assert ids() == [second_job_session, first_job_session]
    assert ids(job_id=world.job_id) == [first_job_session] and ids(job_id=second) == [second_job_session]
    assert ids(job_id=other_world.job_id) == [] and ids(job_id=999_999) == []  # not a 404, and nothing of another seeker's


@pytest.mark.parametrize("name, value", [("job_id", 0), ("job_id", -1), ("job_id", 999_999), ("before_id", 0), ("before_id", -3)])
def test_a_non_positive_or_unknown_id_is_an_empty_page_and_not_a_404(api, db, clock, name, value):
    world = build_world(db)
    add(db, world, clock, S.COMPLETED)
    body = ok(get(api, world, **{name: value}))
    assert body["items"] == [] and body["next_before_id"] is None and body["active"] is None


# ── The active session ──


@pytest.mark.parametrize("label, status, deadline, advance, expected", CASES, ids=[case[0] for case in CASES])
def test_active_follows_the_lifecycle_and_a_read_changes_no_row(api, db, clock, label, status, deadline, advance, expected):
    world = build_world(db)
    session_id = add(db, world, clock, status, deadline=deadline)
    stored = physical(db, session_id)
    clock.advance(advance)
    body = ok(get(api, world))
    assert "active" in body  # always present: null when there is none
    if expected is None:
        assert body["active"] is None
    else:
        assert body["active"]["id"] == session_id and body["active"]["status"] == expected
        assert body["active"] in body["items"]  # on the page, so in both, as the same summary
    assert physical(db, session_id) == stored


@pytest.mark.parametrize("status", [S.PLANNING, S.CREATED, S.LIVE])
def test_a_stale_session_is_aborted_in_the_items_and_is_not_active(api, db, clock, status):
    world = build_world(db)
    session_id = add(db, world, clock, status, deadline=-1 - (settings.INTERVIEW_END_GRACE_SECONDS if status == S.LIVE else 0))
    body = ok(get(api, world))
    assert body["active"] is None
    assert [(i["id"], i["status"], i["end_reason"], i["joinable"]) for i in body["items"]] == [(session_id, "aborted", STALE_REASON[status], False)]
    assert physical(db, session_id)[0] == status  # the GET did not settle it


def test_active_does_not_depend_on_limit_before_id_or_job_id(api, db, clock):
    world = build_world(db)
    other = new_job(db, world)
    active = add(db, world, clock, S.CREATED, deadline=300)  # the oldest row
    done = [add(db, world, clock, S.COMPLETED) for _ in range(2)]
    done_elsewhere = add(db, world, clock, S.COMPLETED, job_id=other)

    by_limit = ok(get(api, world, limit=1))
    assert [i["id"] for i in by_limit["items"]] == [done_elsewhere] and by_limit["active"]["id"] == active
    by_cursor = ok(get(api, world, before_id=active))
    assert by_cursor["items"] == [] and by_cursor["active"]["id"] == active  # not in the items, still active
    by_job = ok(get(api, world, job_id=other))
    assert [i["id"] for i in by_job["items"]] == [done_elsewhere] and by_job["active"]["id"] == active and by_job["active"]["job_id"] == world.job_id
    nowhere = ok(get(api, world, job_id=999_999, limit=1, before_id=1))
    assert nowhere["items"] == [] and nowhere["active"]["id"] == active
    assert [i["id"] for i in ok(get(api, world))["items"]] == [done_elsewhere, *done[::-1], active]  # and on the full page it is one of the items


def test_active_on_the_page_is_the_same_summary_as_its_item(api, db, clock):
    world = build_world(db)
    add(db, world, clock, S.COMPLETED)
    active = add(db, world, clock, S.LIVE, deadline=600)
    for params in ({}, {"limit": 1}):
        body = ok(get(api, world, **params))
        assert body["items"][0]["id"] == active and body["active"] == body["items"][0]


def test_another_seekers_active_session_is_never_shown(api, db, clock):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    theirs = add(db, other, clock, S.CREATED, deadline=300)
    body = ok(get(api, world))
    assert body["active"] is None and body["items"] == []
    mine = add(db, world, clock, S.CREATED, deadline=300)
    assert ok(get(api, world))["active"]["id"] == mine and [i["id"] for i in ok(get(api, other))["items"]] == [theirs]
    assert ok(get(api, other))["active"]["id"] == theirs


def test_a_session_created_over_http_is_the_active_one_with_the_dates_of_the_clock(api, db, clock):
    world = build_world(db)
    created = api.post(f"/api/jobs/{world.job_id}/interview-sessions", headers=auth(world.user), json=VALID)
    assert created.status_code == 201, created.text
    session = created.json()["session"]
    quota_before = quota_rows(db)
    assert quota_before  # the create took its reservations
    body = ok(get(api, world))
    active = body["active"]
    assert (active["id"], active["status"], active["joinable"], active["job_title"], active["feedback_status"]) == (session["id"], "created", True, "Backend Engineer", "none")
    assert at(active["created_at"]) == clock.now and at(active["active_until"]) == clock.now + timedelta(seconds=settings.INTERVIEW_JOIN_SECONDS)
    assert at(active["expires_at"]) == clock.now + timedelta(days=settings.INTERVIEW_RETENTION_DAYS)
    assert body["items"] == [active] and quota_rows(db) == quota_before  # reading it costs nothing


def test_after_the_seeker_ends_the_session_active_is_null(api, db, clock):
    world = build_world(db)
    session_id = api.post(f"/api/jobs/{world.job_id}/interview-sessions", headers=auth(world.user), json=VALID).json()["session"]["id"]
    assert ok(get(api, world))["active"]["id"] == session_id
    interview_service.end(db, world.user, session_id, clock=clock)  # the end route is a later stage; the service is what it will call
    body = ok(get(api, world))
    assert body["active"] is None
    assert [(i["id"], i["status"], i["end_reason"]) for i in body["items"]] == [(session_id, "aborted", "seeker_ended")]


# ── Retention, consent, and what a read does not do ──


def test_the_seekers_own_expired_sessions_are_purged_and_another_seekers_are_not(api, db, clock):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    mine = add(db, world, clock, S.COMPLETED, expires_in=-1)
    theirs = add(db, other, clock, S.COMPLETED, expires_in=-1)
    kept = add(db, world, clock, S.COMPLETED)
    assert [item["id"] for item in ok(get(api, world))["items"]] == [kept]
    db.expire_all()
    assert db.get(InterviewSession, mine) is None and db.get(InterviewSession, theirs) is not None  # the lazy purge is the seeker's own (D65)


def test_an_expired_active_session_is_not_active(api, db, clock):
    world = build_world(db)
    add(db, world, clock, S.CREATED, deadline=1000, expires_in=100)
    clock.advance(100)
    body = ok(get(api, world))
    assert body["active"] is None and body["items"] == []


def test_the_history_is_still_readable_after_the_ai_consent_is_withdrawn(api, db, clock):
    world = build_world(db, ai_consent=False)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    body = ok(get(api, world))
    assert body["active"]["id"] == session_id and [i["id"] for i in body["items"]] == [session_id]  # D67 (8): list stays available


def test_the_history_calls_no_model_and_takes_no_quota(api, db, clock, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the history reached a model or an embedder")

    monkeypatch.setattr(ai_runtime, "llm", boom)
    monkeypatch.setattr(ai_runtime, "embedder", boom)
    world = build_world(db)
    add(db, world, clock, S.CREATED, deadline=300)
    add(db, world, clock, S.COMPLETED)
    ok(get(api, world))
    assert quota_rows(db) == []


# ── Parameters that are not integers ──


@pytest.mark.parametrize(
    "name, value",
    [("limit", "abc"), ("limit", "1.5"), ("limit", ""), ("job_id", "abc"), ("job_id", ""), ("before_id", "abc"), ("before_id", SECRET)],
)
def test_a_parameter_that_is_not_an_integer_is_a_sanitized_422(api, db, name, value):
    world = build_world(db)
    response = get(api, world, **{name: value})
    assert response.status_code == 422 and no_store(response), response.text
    detail = response.json()["detail"]
    assert detail and all(set(error) == {"type", "loc", "msg"} and error["loc"] == ["query", name] for error in detail)  # D68
    assert SECRET not in response.text and (not value or value not in response.text)  # the submitted value is never echoed


def test_an_unknown_query_parameter_is_ignored(api, db, clock):
    world = build_world(db)
    session_id = add(db, world, clock, S.COMPLETED)
    assert [i["id"] for i in ok(get(api, world, **{SECRET: "1"}))["items"]] == [session_id]


# ── Ids outside the range of the id columns ──

# `job_postings.id`, `interview_sessions.id` and `interview_sessions.job_id` are `Integer` (signed 32-bit on PostgreSQL; migrations 0001 and
# 0012), so `job_id` and `before_id` are bounded to that range. An id outside it cannot name a row, and an id outside the signed 64-bit range
# is a bound parameter that SQLite cannot store (a driver error, which was a 500): it is a 422 now, and `limit` keeps its clamp, no bound.
INT32_MAX, INT32_MIN = 2**31 - 1, -(2**31)
OUT_OF_RANGE = [  # (label, value, the error type)
    ("one above the maximum", INT32_MAX + 1, "less_than_equal"),
    ("2**63", 2**63, "less_than_equal"),
    ("10**30", 10**30, "less_than_equal"),
    ("a 5000-digit number", "9" * 5000, "int_parsing_size"),
    ("one below the minimum", INT32_MIN - 1, "greater_than_equal"),
    ("-2**63-1", -(2**63) - 1, "greater_than_equal"),
    ("-10**30", -(10**30), "greater_than_equal"),
    ("a 5000-digit negative number", "-" + "9" * 5000, "int_parsing_size"),
]
FIXED_MESSAGES = {  # the only text a bound error may carry: the fixed bound of the schema, never the submitted value
    "less_than_equal": f"Input should be less than or equal to {INT32_MAX}",
    "greater_than_equal": f"Input should be greater than or equal to {INT32_MIN}",
    "int_parsing_size": "Unable to parse input string as an integer, exceeded maximum size",
}


@pytest.mark.parametrize("name", ["job_id", "before_id"])
@pytest.mark.parametrize("label, value, error_type", OUT_OF_RANGE, ids=[case[0] for case in OUT_OF_RANGE])
def test_an_id_outside_the_32_bit_range_is_a_sanitized_422_and_never_a_500(api, db, clock, name, label, value, error_type):
    world = build_world(db)
    add(db, world, clock, S.CREATED, deadline=300)
    response = get(api, world, **{name: value})
    assert response.status_code == 422 and no_store(response), response.text
    body = response.json()
    assert set(body) == {"detail"}  # no items and no active session in an error
    (error,) = body["detail"]
    assert set(error) == {"type", "loc", "msg"} and error["loc"] == ["query", name]  # D68: no `input`, no `ctx`
    assert (error["type"], error["msg"]) == (error_type, FIXED_MESSAGES[error_type])
    assert str(value) not in response.text  # the submitted value is not in the body, in any form


def test_the_ids_at_the_ends_of_the_32_bit_range_are_accepted_and_active_does_not_change(api, db, clock):
    world = build_world(db)
    done = add(db, world, clock, S.COMPLETED)
    active = add(db, world, clock, S.CREATED, deadline=300)

    def page(**params) -> dict:
        return ok(get(api, world, **params))

    assert [i["id"] for i in page(before_id=INT32_MAX)["items"]] == [active, done]  # every id is below the maximum
    assert page(before_id=INT32_MIN)["items"] == []
    assert page(job_id=INT32_MAX)["items"] == [] and page(job_id=INT32_MIN)["items"] == []  # no such job: an empty page, not a 404
    for params in (
        {"before_id": INT32_MAX}, {"before_id": INT32_MIN}, {"job_id": INT32_MAX}, {"job_id": INT32_MIN},
        {"job_id": INT32_MAX, "before_id": INT32_MIN, "limit": 1},
    ):
        assert page(**params)["active"]["id"] == active, params  # at the ends of the range too


def test_limit_has_no_bound_and_the_service_still_clamps_it(api, db, clock):
    world = build_world(db)
    for _ in range(settings.INTERVIEW_HISTORY_MAX_LIMIT + 1):
        add(db, world, clock, S.COMPLETED)
    assert len(ok(get(api, world, limit=10**30))["items"]) == settings.INTERVIEW_HISTORY_MAX_LIMIT
    assert len(ok(get(api, world, limit=-(10**30)))["items"]) == 1
    response = get(api, world, limit="9" * 5000)  # what the integer parser refuses stays a 422, as before
    assert response.status_code == 422 and no_store(response)
    assert [e["loc"] for e in response.json()["detail"]] == [["query", "limit"]]


# ── The path ──


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_other_methods_are_405(api, db, method):
    world = build_world(db)
    response = api.request(method, URL, headers=auth(world.user))
    assert response.status_code == 405 and "GET" in response.headers["allow"] and no_store(response)


def test_the_trailing_slash_redirects(api):
    response = api.get(URL + "/", follow_redirects=False)  # the router redirects before any dependency runs: no token needed
    assert response.status_code == 307 and response.headers["location"].endswith(URL) and no_store(response)
