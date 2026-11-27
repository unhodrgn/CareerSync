"""What every route under `/api/interview-sessions/{session_id}` has in common (M4 S4.4; docs/DECISIONS.md D67, D68, D69).

The routes of one session (detail, end, delete) read the same path id, ask the same service check (seeker, ownership, expiry) and answer
the same way to the same bad requests, so the cases that do not depend on what a route does are written once, over the table `OPERATIONS`.
Each step of S4.4 adds the route it registers to the table; what a route does (its body, its writes) is in its own file, starting with
test_interview_api_detail.py, test_interview_api_end.py, test_interview_api_delete.py and test_interview_api_feedback.py. Every status asserted here is asserted together with `Cache-Control: no-store`. The clock reaches the services
through the overridable dependency `get_clock`, and a tripwire makes any read of the real clock by the time and quota services fail.
The id is a signed 32-bit integer, like the id column: outside that range, or not an integer, it is a sanitized 422 (D68) and no service is
called, so nothing is read, settled, purged or deleted; inside it, an id that names no session of the seeker is a 404."""
import pytest
from fastapi.testclient import TestClient

from ai.interview import FeedbackReport
from app.api.v1.interview_sessions import get_clock
from app.db.session import get_db
from app.main import app
from app.models.interview import InterviewStatus as S
from app.services import ai_runtime, interview_time
from app.services import interview_quota_service as quota_service

from .conftest import auth
from .interview_fixtures import Clock, build_world
from .test_interview_api_history import FIXED_MESSAGES, INT32_MAX, INT32_MIN, OUT_OF_RANGE
from .test_interview_history_active import add, physical, quota_rows

URL = "/api/interview-sessions"
# (name, method, what follows the session id in the path, the status of a success). Grows with each step of S4.4.
DETAIL = ("detail", "get", "", 200)
END = ("end", "post", "/end", 200)
DELETE = ("delete", "delete", "", 204)
FEEDBACK = ("feedback", "post", "/feedback", 200)
OPERATIONS = [DETAIL, END, DELETE, FEEDBACK]
# A report that the feedback route answers 200 for with no model: a stored one (`to_data()` of an empty rules report)
STORED_REPORT = FeedbackReport("rules", (), (), (), (), (), (), ()).to_data()
EACH = pytest.mark.parametrize("op", OPERATIONS, ids=[op[0] for op in OPERATIONS])
MESSAGES = {**FIXED_MESSAGES, "int_parsing": "Input should be a valid integer, unable to parse string as an integer"}
BAD_IDS = list(OUT_OF_RANGE) + [(f"not an integer: {value}", value, "int_parsing") for value in ("abc", "1.5", "0x10")]


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


def call(api, op, session_id, user=None, **kwargs):
    """The request of `op` for `session_id`, as `user` (no token when it is None); `headers=` replaces the token."""
    _name, method, suffix, _success = op
    headers = kwargs.pop("headers", None) or (auth(user) if user is not None else None)
    return api.request(method, f"{URL}/{session_id}{suffix}", headers=headers, **kwargs)


def success_session(db, world, clock, op):
    """A session for which `op` answers `op[3]`: a created one, and for the feedback a finished one with a stored report (no model, no quota)."""
    if op is FEEDBACK:
        return add(db, world, clock, S.COMPLETED, feedback=STORED_REPORT, feedback_method="rules", feedback_prompt_version="v2", feedback_at=clock())
    return add(db, world, clock, S.CREATED, deadline=300)


def no_store(response) -> bool:
    return response.headers.get_list("cache-control") == ["no-store"]


# ── Who may ask ──


@EACH
def test_no_token_is_401(api, op):
    response = call(api, op, 1)
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer" and no_store(response)


@EACH
@pytest.mark.parametrize("headers", [{"Authorization": "Bearer not-a-token"}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}])
def test_a_malformed_token_is_401(api, op, headers):
    response = call(api, op, 1, headers=headers)
    assert response.status_code == 401 and no_store(response)


@EACH
def test_a_company_user_gets_403_seeker_only_and_the_session_is_not_touched(api, db, clock, op):
    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    stored = physical(db, session_id)
    company = build_world(db, email="c@interview.test", role="company")
    response = call(api, op, session_id, company.user)
    assert response.status_code == 403 and no_store(response)
    body = response.json()
    assert body["code"] == "SEEKER_ONLY" and isinstance(body["message"], str) and body["message"] and "detail" not in body
    assert physical(db, session_id) == stored


# ── Which session ──


@EACH
def test_another_seekers_session_and_an_unknown_id_are_the_same_404(api, db, clock, op):
    world, other = build_world(db), build_world(db, email="two@interview.test")
    mine = add(db, world, clock, S.CREATED, deadline=300)
    stored = physical(db, mine)
    foreign, unknown = call(api, op, mine, other.user), call(api, op, 999_999, other.user)
    for response in (foreign, unknown):
        assert response.status_code == 404 and no_store(response)
    assert foreign.json() == unknown.json() and foreign.json()["code"] == "INTERVIEW_NOT_FOUND"  # another's session cannot be told from none
    assert physical(db, mine) == stored


@EACH
@pytest.mark.parametrize("session_id", [0, -1, 999_999, INT32_MIN, INT32_MAX])
def test_an_unknown_zero_or_negative_id_inside_the_range_is_a_404(api, db, clock, op, session_id):
    world = build_world(db)
    mine = add(db, world, clock, S.CREATED, deadline=300)
    stored = physical(db, mine)
    response = call(api, op, session_id, world.user)
    assert response.status_code == 404 and no_store(response) and response.json()["code"] == "INTERVIEW_NOT_FOUND"
    assert physical(db, mine) == stored


@EACH
def test_an_expired_session_is_a_404_from_the_instant_it_expires(api, db, clock, op):
    world = build_world(db)
    session_id = add(db, world, clock, S.COMPLETED, expires_in=100)
    clock.advance(100)  # `expires_at` is the instant it goes
    response = call(api, op, session_id, world.user)
    assert response.status_code == 404 and no_store(response) and response.json()["code"] == "INTERVIEW_NOT_FOUND"


# ── An id that is not a 32-bit integer ──


@EACH
@pytest.mark.parametrize("label, value, error_type", BAD_IDS, ids=[case[0] for case in BAD_IDS])
def test_a_bad_id_is_a_sanitized_422_and_nothing_is_read_or_changed(api, db, clock, op, label, value, error_type):
    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    stored, quota_before = physical(db, session_id), quota_rows(db)
    response = call(api, op, value, world.user)
    assert response.status_code == 422 and no_store(response), response.text
    body = response.json()
    assert set(body) == {"detail"}
    (error,) = body["detail"]
    assert set(error) == {"type", "loc", "msg"} and error["loc"] == ["path", "session_id"]  # D68: no `input`, no `ctx`
    assert (error["type"], error["msg"]) == (error_type, MESSAGES[error_type])  # the fixed bound or the fixed sentence, never the value
    assert str(value) not in response.text
    assert physical(db, session_id) == stored and quota_rows(db) == quota_before


# ── The path ──


def test_other_methods_on_a_session_path_are_405_and_say_which_are_allowed(api, db, clock):
    """`Allow` lists every method of the path, in a fixed order: the detail path answers `DELETE, GET` and the end path `POST`. FastAPI keeps one
    route per method and gives a wrong method to the first route that matches, which would advertise its own method only; the interview router
    has a route class that widens that `Allow` (`app/core/allowed_methods.py`)."""
    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    stored = physical(db, session_id)
    for suffix in sorted({op[2] for op in OPERATIONS}):
        allowed = {op[1].upper() for op in OPERATIONS if op[2] == suffix}
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            if method in allowed:
                continue
            response = api.request(method, f"{URL}/{session_id}{suffix}", headers=auth(world.user))
            assert response.status_code == 405 and no_store(response), (method, suffix)
            assert {token.strip() for token in response.headers["allow"].split(",")} == allowed, (method, suffix, response.headers["allow"])
            assert response.headers["allow"] == ", ".join(sorted(allowed)), (method, suffix)  # the same order on every run
    assert physical(db, session_id) == stored  # and the refused request did nothing (a DELETE on the end path, a POST on the delete path)


def test_the_allow_header_of_each_session_path_is_pinned(api, db, clock):
    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    assert api.post(f"{URL}/{session_id}", headers=auth(world.user)).headers["allow"] == "DELETE, GET"  # both methods of the detail path
    assert api.get(f"{URL}/{session_id}/end", headers=auth(world.user)).headers["allow"] == "POST"


@EACH
def test_the_trailing_slash_redirects(api, op):
    response = api.request(op[1], f"{URL}/5{op[2]}/", follow_redirects=False)  # the router redirects before any dependency runs: no token needed
    assert response.status_code == 307 and response.headers["location"].endswith(f"{URL}/5{op[2]}") and no_store(response)


# ── What no route of the session uses ──


@EACH
def test_it_works_after_the_ai_consent_is_withdrawn(api, db, clock, op):
    world = build_world(db, ai_consent=False)
    session_id = success_session(db, world, clock, op)
    response = call(api, op, session_id, world.user)
    assert response.status_code == op[3] and no_store(response), response.text  # D67 (8): and a stored feedback is still read


@EACH
def test_it_calls_no_model_and_takes_no_quota(api, db, clock, op, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a route of the session reached a model or an embedder")

    monkeypatch.setattr(ai_runtime, "llm", boom)
    monkeypatch.setattr(ai_runtime, "embedder", boom)
    world = build_world(db)
    session_id = success_session(db, world, clock, op)
    assert call(api, op, session_id, world.user).status_code == op[3]
    assert quota_rows(db) == []
