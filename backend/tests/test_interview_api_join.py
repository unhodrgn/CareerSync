"""`POST /api/interview-sessions/{session_id}/join` (M5 S4; docs/DECISIONS.md D56, D58, D80 (4)): the microphone-only LiveKit token.

The route calls `interview_join_service.issue`. These tests decode the token it signs and show what it can and cannot do: one room (the
room of the session, an HMAC of its id), the microphone only, no data, a short life that never outlasts the join time, a random identity, and
a dispatch of the Interview Agent whose metadata is the session id and nothing else. They also show every refusal in the order of its checks,
that nothing is written or reserved, and the contract of the route. No network: the token is signed locally, and no LiveKit server is
contacted. Time is the test clock, and the database is the SQLite fixture."""
import json
from datetime import datetime, timedelta

import jwt
import pytest
from livekit import api as livekit

from app.core import agent_auth
from app.core.config import settings
from app.main import app
from app.models import InterviewTurn
from app.models.interview import InterviewStatus as S
from app.services.interview_time import as_utc

from .conftest import auth
from .interview_fixtures import build_world
from .test_interview_api_history import OUT_OF_RANGE
from .test_interview_api_session_common import api, clock, no_store, no_wall_clock  # noqa: F401 (the fixtures)
from .test_interview_history_active import add, physical, quota_rows
from .test_interview_internal_api import SECRET as AGENT_SECRET

URL = "/api/interview-sessions"
LIVEKIT_URL = "wss://careersync-test.livekit.cloud"
KEY, SECRET = "APIkeyForTests", "livekit-secret-" + "x" * 30


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "LIVEKIT_URL", LIVEKIT_URL)
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", KEY)
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", SECRET)
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", AGENT_SECRET)


def join(api, session_id, user=None, **kwargs):
    headers = kwargs.pop("headers", None) or (auth(user) if user is not None else None)
    return api.post(f"{URL}/{session_id}/join", headers=headers, **kwargs)


def claims(token: str):
    return livekit.TokenVerifier(KEY, SECRET).verify(token)


def raw(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False, "verify_nbf": False})


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def created(db, world, clock):
    return add(db, world, clock, S.CREATED, deadline=300)


# ── What the token is ──


def test_a_created_session_gets_a_token_for_its_own_room_and_the_microphone_only(api, db, world, clock, created):
    response = join(api, created, world.user)
    assert response.status_code == 200 and no_store(response), response.text
    body = response.json()
    assert set(body) == {"url", "token", "room", "expires_at"}
    assert body["url"] == LIVEKIT_URL and body["room"] == agent_auth.room_name(created, AGENT_SECRET)
    c = claims(body["token"])
    assert c.identity.startswith("candidate-") and c.name == "Candidate"
    v = c.video
    assert (v.room_join, v.room) == (True, body["room"])
    assert (v.can_publish, v.can_subscribe, v.can_publish_data) == (True, True, False)
    assert list(v.can_publish_sources) == ["microphone"]  # never a camera or a screen
    assert not (v.room_create or v.room_list or v.room_admin or v.room_record or v.ingress_admin or v.hidden or v.recorder or v.agent)
    assert not c.sip and not c.attributes and not c.metadata


def test_the_token_dispatches_the_agent_with_the_session_id_as_the_only_metadata(api, db, world, clock, created):
    body = join(api, created, world.user).json()
    config = claims(body["token"]).room_config
    (dispatch,) = config.agents
    assert dispatch.agent_name == settings.INTERVIEW_AGENT_NAME == "careersync-interviewer"
    assert json.loads(dispatch.metadata) == {"session_id": created} and dispatch.metadata == json.dumps({"session_id": created})
    assert (config.max_participants, config.empty_timeout, config.departure_timeout) == (3, 30, 30)
    assert not config.name and not config.metadata, "the room is the one of the grant; nothing is added to it"
    for secret in (KEY, SECRET, AGENT_SECRET):  # the browser reads the token: no secret is in it, or in the response
        assert secret not in body["token"] and secret not in json.dumps(body)
    assert "seeker" not in json.dumps(raw(body["token"])).lower() and world.user.email not in json.dumps(raw(body["token"]))


def test_the_token_is_short_lived_and_never_outlasts_the_join_time(api, db, world, clock, created):
    body = join(api, created, world.user).json()
    c = raw(body["token"])
    assert c["exp"] - c["nbf"] == settings.INTERVIEW_JOIN_TOKEN_TTL_SECONDS == 120
    assert as_utc(datetime.fromisoformat(body["expires_at"])) == clock.now + timedelta(seconds=120)
    other = build_world(db, email="two@interview.test")
    near = add(db, other, clock, S.CREATED, deadline=45)  # the join deadline is 45 s away: the token is capped by it
    capped = join(api, near, other.user).json()
    c45 = raw(capped["token"])
    assert c45["exp"] - c45["nbf"] == 45
    assert as_utc(datetime.fromisoformat(capped["expires_at"])) == clock.now + timedelta(seconds=45)


def test_on_the_join_deadline_the_token_lives_one_second(api, db, world, clock, created):
    clock.advance(300)  # the deadline is inclusive
    response = join(api, created, world.user)
    assert response.status_code == 200
    c = raw(response.json()["token"])
    assert c["exp"] - c["nbf"] == 1


def test_every_join_has_a_new_identity_in_the_same_room(api, world, created):
    first, second = join(api, created, world.user).json(), join(api, created, world.user).json()
    assert first["room"] == second["room"] and claims(first["token"]).identity != claims(second["token"]).identity


def test_the_room_of_another_session_is_another_room_and_follows_the_agent_secret(api, db, world, clock, created, monkeypatch):
    other = build_world(db, email="two@interview.test")
    other_session = add(db, other, clock, S.CREATED, deadline=300)
    assert join(api, other_session, other.user).json()["room"] != join(api, created, world.user).json()["room"]
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", "another-agent-secret-" + "z" * 20)
    assert join(api, created, world.user).json()["room"] != agent_auth.room_name(created, AGENT_SECRET)


def test_the_room_name_is_the_one_the_agent_checks(api, db, world, clock, created):
    """The browser's room and the internal API's binding are one formula: the agent in this room can read this session's context."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db

    room = join(api, created, world.user).json()["room"]
    app.dependency_overrides[get_db] = lambda: db
    ok = TestClient(app).get(
        f"/api/internal/interview-sessions/{created}/context", headers={agent_auth.SECRET_HEADER: AGENT_SECRET, agent_auth.ROOM_HEADER: room}
    )
    assert ok.status_code == 200 and ok.json()["status"] == "created"


def test_a_join_changes_nothing_and_takes_no_quota(api, db, world, clock, created):
    stored, quota_before = physical(db, created), quota_rows(db)
    assert join(api, created, world.user).status_code == 200
    assert physical(db, created) == stored and quota_rows(db) == quota_before
    assert db.query(InterviewTurn).count() == 0


# ── Who may join, in the order of the checks ──


def test_no_token_and_a_malformed_token_are_401(api, created):
    for headers in (None, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}):
        response = join(api, created, headers=headers)
        assert response.status_code == 401 and no_store(response) and "token" not in response.json()


def test_a_company_user_gets_403_seeker_only(api, db, created, clock):
    company = build_world(db, email="c@interview.test", role="company")
    response = join(api, created, company.user)
    assert response.status_code == 403 and no_store(response) and response.json()["code"] == "SEEKER_ONLY"


def test_another_seekers_session_an_unknown_id_and_an_expired_session_are_the_same_404(api, db, world, clock, created):
    other = build_world(db, email="two@interview.test")
    expiring = add(db, other, clock, S.CREATED, deadline=300, expires_in=100)
    foreign, unknown = join(api, created, other.user), join(api, 999_999, other.user)
    clock.advance(100)
    expired = join(api, expiring, other.user)
    for response in (foreign, unknown, expired):
        assert response.status_code == 404 and no_store(response) and "token" not in response.text
    assert foreign.json() == unknown.json() == expired.json() and foreign.json()["code"] == "INTERVIEW_NOT_FOUND"


@pytest.mark.parametrize("label, value, error_type", list(OUT_OF_RANGE) + [("not an integer", "abc", "int_parsing")])
def test_a_bad_id_is_a_sanitized_422(api, world, label, value, error_type):
    response = join(api, value, world.user)
    assert response.status_code == 422 and no_store(response)
    (error,) = response.json()["detail"]
    assert set(error) == {"type", "loc", "msg"} and error["loc"] == ["path", "session_id"] and str(value) not in response.text


def test_without_the_current_ai_consent_it_is_the_consent_error_whatever_the_session_is(api, db, world, clock, created):
    from app.services import interview_service

    expected = {"code": "AI_CONSENT_REQUIRED", "message": interview_service.consent_required_error().message}
    world.user.consent_ai_at = None
    live_world = build_world(db, email="two@interview.test")  # a live session is "not joinable", but the consent is checked first
    live_world.user.consent_ai_at = None
    live = add(db, live_world, clock, S.LIVE, deadline=300)
    db.commit()
    for user, session_id in ((world.user, created), (live_world.user, live)):
        response = join(api, session_id, user)
        assert response.status_code == 409 and no_store(response) and response.json() == expected


def test_a_session_that_is_not_created_is_refused_and_a_planning_one_says_so(api, db, world, clock):
    cases = [
        (S.PLANNING, 120, 409, "INTERVIEW_PLANNING", None),
        (S.LIVE, 600, 409, "INTERVIEW_NOT_JOINABLE", "live"),
        (S.COMPLETED, None, 409, "INTERVIEW_NOT_JOINABLE", "completed"),
        (S.ABORTED, None, 409, "INTERVIEW_NOT_JOINABLE", "aborted"),
    ]
    for index, (status, deadline, http, code, status_in_body) in enumerate(cases):
        seeker = build_world(db, email=f"seeker{index}@interview.test")
        session_id = add(db, seeker, clock, status, deadline=deadline)
        response = join(api, session_id, seeker.user)
        assert (response.status_code, response.json()["code"]) == (http, code), (status, response.text)
        assert response.json().get("status") == status_in_body and no_store(response) and "token" not in response.text


def test_a_session_past_its_join_deadline_is_not_joinable(api, db, world, clock, created):
    clock.advance(300.001)
    response = join(api, created, world.user)
    assert (response.status_code, response.json()["code"], response.json()["status"]) == (409, "INTERVIEW_NOT_JOINABLE", "aborted")


@pytest.mark.parametrize("missing", ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "INTERVIEW_AGENT_SECRET"])
def test_an_unconfigured_voice_service_is_503_after_every_other_check(api, db, world, clock, created, monkeypatch, missing):
    monkeypatch.setattr(settings, missing, "")
    other = build_world(db, email="two@interview.test")
    assert join(api, created, other.user).status_code == 404  # not the owner: nothing about the configuration is told
    response = join(api, created, world.user)
    assert response.status_code == 503 and no_store(response)
    assert response.json() == {"code": "INTERVIEW_VOICE_UNAVAILABLE", "message": "음성 면접을 지금은 준비할 수 없습니다."}


def test_a_short_agent_secret_is_not_configured(api, world, created, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", "x" * (settings.INTERVIEW_AGENT_SECRET_MIN_CHARS - 1))
    assert join(api, created, world.user).status_code == 503


# ── The path and the contract ──


def test_the_path_takes_post_only_and_redirects_a_trailing_slash(api, world, created):
    for method in ("GET", "PUT", "PATCH", "DELETE"):
        response = api.request(method, f"{URL}/{created}/join", headers=auth(world.user))
        assert response.status_code == 405 and no_store(response) and response.headers["allow"] == "POST", method
    redirect = api.post(f"{URL}/5/join/", follow_redirects=False)
    assert redirect.status_code == 307 and redirect.headers["location"].endswith(f"{URL}/5/join") and no_store(redirect)


def test_the_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-sessions/{session_id}/join"]
    assert set(operation) == {"post"}
    post = operation["post"]
    assert post["tags"] == ["interview"] and post["security"] == [{"HTTPBearer": []}] and "requestBody" not in post
    assert post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/JoinOut")
    schema = spec["components"]["schemas"]["JoinOut"]
    assert set(schema["properties"]) == {"url", "token", "room", "expires_at"} and set(schema["required"]) == {"url", "token", "room", "expires_at"}
    assert not [name for name in schema["properties"] if "weight" in name.lower() or name == "notice"]  # no AI result is in it
