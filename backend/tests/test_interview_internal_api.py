"""The internal agent API of the practice interview (M5 S1; docs/DECISIONS.md D58, D79), on the real application.

`GET /api/internal/interview-sessions/{id}/context` and `POST …/events`: the shared secret and the room binding (`app/core/agent_auth.py`),
what the context gives and never gives, and that the events route keeps the ingestion service's contract over HTTP. A real engine plays
the agent (`HttpAgent`, the `Agent` of interview_fixtures.py with its events sent as JSON). Time is the test clock; the database is the
SQLite fixture. The service's own rules are tested in the test_interview_ingest_* files; these tests show the HTTP layer adds nothing and
loses nothing."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.api.v1.interview_sessions import get_clock
from app.core import agent_auth
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewSession, User
from app.services import interview_ingest_service as ingest

from .conftest import auth
from .interview_fixtures import Agent, Clock, build_world, new_session, turn_rows

SECRET = "agent-secret-" + "k" * 30
BASE = "/api/internal/interview-sessions"
ANSWER = "Java와 Spring Boot로 주문 API를 만들고 트랜잭션 경계를 정리했습니다. 테스트 커버리지도 높였습니다."
CONTEXT_KEYS = {
    "session_id", "status", "end_reason", "joinable", "accepting_turns", "end_grace_open", "active_until", "plan", "plan_sha256", "limits",
    "last_seq", "ai_consent", "mask_names",
}


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", SECRET)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def api(db, clock):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def world(db):
    w = build_world(db)
    w.user.display_name = "김민준"
    db.commit()
    return w


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


def headers(session_id: int, *, secret: str | None = SECRET, room: str | None = None) -> dict:
    out = {}
    if secret is not None:
        out[agent_auth.SECRET_HEADER] = secret
    room = agent_auth.room_name(session_id, SECRET) if room is None else room
    if room != "-":
        out[agent_auth.ROOM_HEADER] = room
    return out


def context(api, session_id, **kw):
    return api.get(f"{BASE}/{session_id}/context", headers=headers(session_id, **kw))


def event(api, session_id, body, **kw):
    return api.post(f"{BASE}/{session_id}/events", json=body, headers=headers(session_id, **kw))


def no_store(response) -> bool:
    return response.headers.get_list("cache-control") == ["no-store"]


def turn_body(e: ingest.TurnEvent) -> dict:
    return {"type": "turn", "turn": dataclasses.asdict(e)}


def end_body(e: ingest.EndEvent) -> dict:
    return {"type": "end", "coverage": dict(e.coverage), "closing": dataclasses.asdict(e.closing) if e.closing is not None else None}


class HttpAgent(Agent):
    """The test agent of interview_fixtures.py, with its events posted to the internal route instead of called on the service."""

    def __init__(self, db, api, session_id, clock, **kw):
        super().__init__(db, session_id, clock, **kw)
        self.api = api
        self.responses = []

    def _send(self, call, e):
        self.events.append(e)
        body = turn_body(e) if call is ingest.record_turn else end_body(e)
        response = event(self.api, self.session_id, body)
        self.responses.append(response)
        return response


# ── Who may call ──


@pytest.mark.parametrize("kw", [{"secret": None}, {"secret": ""}, {"secret": SECRET[:-1]}, {"secret": SECRET + "x"}], ids=["none", "empty", "short", "long"])
def test_a_missing_or_wrong_secret_is_401_with_a_fixed_body(api, sid, kw):
    for response in (context(api, sid, **kw), event(api, sid, {"type": "turn"}, **kw)):
        assert response.status_code == 401 and no_store(response)
        assert response.json() == {"code": "AGENT_UNAUTHORIZED", "message": "인증되지 않은 요청입니다."}


def test_an_unset_or_short_secret_on_the_server_refuses_even_the_matching_value(api, sid, monkeypatch):
    for value in ("", "short-secret"):
        monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", value)
        response = context(api, sid, secret=value, room=agent_auth.room_name(sid, value))
        assert response.status_code == 401 and no_store(response)


def test_a_seeker_token_is_not_the_agent_secret(api, world, sid):
    response = api.get(f"{BASE}/{sid}/context", headers=auth(world.user))
    assert response.status_code == 401 and response.json()["code"] == "AGENT_UNAUTHORIZED"


def test_the_secret_is_checked_before_the_path_and_the_body(api):
    for path in (f"{BASE}/abc/context", f"{BASE}/99999999999/context"):
        response = api.get(path)
        assert response.status_code == 401 and no_store(response)
    response = api.post(f"{BASE}/abc/events", json={"type": "nonsense", "답변": 1})
    assert response.status_code == 401 and "답변" not in response.text
    # A body that is not JSON at all is refused by FastAPI while it reads the request, before any dependency: a sanitized 422 that repeats
    # nothing of what was sent (D68), which tells a caller without the secret nothing about the session
    response = api.post(f"{BASE}/abc/events", content="답변 not json".encode(), headers={"content-type": "application/json"})
    assert response.status_code == 422 and "답변" not in response.text and no_store(response)


@pytest.mark.parametrize("room", ["-", "", "cs-iv-0", "other"], ids=["missing", "empty", "short", "other"])
def test_a_room_that_is_not_the_sessions_is_the_same_404_as_an_unknown_session(api, sid, room):
    unknown = context(api, sid + 1000)
    for response in (context(api, sid, room=room), event(api, sid, {"type": "turn"}, room=room)):
        assert response.status_code == 404 and no_store(response)
        assert response.json() == unknown.json() == {"code": "INTERVIEW_NOT_FOUND", "message": "모의 면접을 찾을 수 없습니다."}


def test_the_room_of_another_session_does_not_open_this_one(api, db, sid, clock):
    other = build_world(db, email="s2@interview.test")
    other_sid = new_session(db, other, clock)
    assert context(api, sid, room=agent_auth.room_name(other_sid, SECRET)).status_code == 404
    assert context(api, other_sid).status_code == 200


def test_a_bad_id_with_the_secret_is_a_sanitized_422(api):
    response = api.get(f"{BASE}/abc/context", headers={agent_auth.SECRET_HEADER: SECRET, agent_auth.ROOM_HEADER: "x"})
    assert response.status_code == 422 and no_store(response)
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])


# ── The context ──


def test_the_context_of_a_created_session(api, db, sid):
    response = context(api, sid)
    assert response.status_code == 200 and no_store(response)
    body = response.json()
    assert set(body) == CONTEXT_KEYS
    row = db.get(InterviewSession, sid)
    assert body["session_id"] == sid and body["status"] == "created" and body["joinable"] and body["accepting_turns"]
    assert body["plan"] == row.plan and body["plan_sha256"] == row.plan_sha256 and body["limits"] == row.limits
    assert body["last_seq"] == 0 and body["ai_consent"] is True and body["mask_names"] == ["김민준"]
    assert not body["end_grace_open"] and body["end_reason"] is None


def test_the_context_carries_no_cv_no_email_no_weight_no_feedback(api, db, world, sid):
    text = context(api, sid).text
    assert world.user.email not in text and "s1@interview.test" not in text
    for absent in ("weight", "feedback", "coverage", "masked_text", "cv_quote\": \"", "홍길동", "테헤란로", "병역"):
        assert absent not in text, absent


def test_a_seeker_without_a_display_name_gives_no_mask_names(api, db, world, sid):
    world.user.display_name = "  "
    db.commit()
    assert context(api, sid).json()["mask_names"] == []


def test_the_context_follows_the_session(api, db, world, sid, clock):
    agent = HttpAgent(db, api, sid, clock)
    agent.start()
    agent.answer(ANSWER)
    body = context(api, sid).json()
    assert body["status"] == "live" and body["last_seq"] == len(turn_rows(db, sid)) and body["last_seq"] >= 3
    db.get(User, world.user.id).consent_ai_at = None
    db.commit()
    assert context(api, sid).json()["ai_consent"] is False  # read by the agent before each model call (D80, stage S3)


def test_the_context_of_a_deleted_or_expired_session_is_404(api, db, world, sid, clock):
    assert api.delete(f"/api/interview-sessions/{sid}", headers=auth(world.user)).status_code == 204
    assert context(api, sid).status_code == 404
    other = build_world(db, email="s3@interview.test")
    other_sid = new_session(db, other, clock)
    clock.advance(settings.INTERVIEW_RETENTION_DAYS * 86400 + 1)
    response = context(api, other_sid)
    assert response.status_code == 404 and no_store(response)


def test_the_context_of_an_ended_session_says_so(api, world, sid):
    assert api.post(f"/api/interview-sessions/{sid}/end", headers=auth(world.user)).status_code == 200
    body = context(api, sid).json()
    assert body["status"] == "aborted" and body["end_reason"] == "seeker_ended" and not body["accepting_turns"]


# ── The events ──


def test_a_whole_interview_over_http_completes_and_its_feedback_works(api, db, world, sid, clock):
    agent = HttpAgent(db, api, sid, clock)
    agent.start()
    for _ in range(40):
        if agent.engine.state.phase.value in ("ended", "aborted"):
            break
        agent.answer(ANSWER)
    assert agent.engine.state.phase.value == "ended"
    assert all(r.status_code == 200 and no_store(r) for r in agent.responses), [r.json() for r in agent.responses if r.status_code != 200]
    last = agent.responses[-1].json()
    assert last == {"type": "end", "outcome": "ended", "status": "completed", "end_reason": last["end_reason"], "seq": None, "started": None, "dropped_quotes": None}
    first = agent.responses[0].json()
    assert first["type"] == "turn" and first["outcome"] == "stored" and first["seq"] == 1 and first["started"] is True
    rows = turn_rows(db, sid)
    assert rows[-1].kind == "closing" and len(rows) == len(agent.engine.state.turns)
    seeker = auth(world.user)
    assert api.get(f"/api/interview-sessions/{sid}", headers=seeker).json()["status"] == "completed"
    feedback = api.post(f"/api/interview-sessions/{sid}/feedback", headers=seeker)
    assert feedback.status_code == 200 and feedback.json()["final"] is True


def test_the_seekers_name_is_masked_again_before_storing(api, db, sid, clock):
    agent = HttpAgent(db, api, sid, clock)
    agent.start()
    agent.answer("저는 김민준이고 " + ANSWER)
    stored = " ".join(row.text for row in turn_rows(db, sid))
    assert "김민준" not in stored


def test_a_repeated_event_is_a_duplicate_and_a_gap_names_the_expected_seq(api, db, sid, clock):
    agent = HttpAgent(db, api, sid, clock)
    agent.start()
    again = event(api, sid, turn_body(agent.events[0]))
    assert again.status_code == 200 and again.json()["outcome"] == "duplicate"
    agent.engine.on_answer(ANSWER, 20.0)
    later = agent.turn_events()[-1]
    gap = event(api, sid, turn_body(later))
    assert gap.status_code == 409 and no_store(gap)
    assert gap.json()["code"] == "INTERVIEW_SEQ_GAP" and gap.json()["expected_seq"] == 2


def test_after_the_seeker_deletes_the_session_every_event_is_404(api, db, world, sid, clock):
    agent = HttpAgent(db, api, sid, clock)
    agent.start()
    assert api.delete(f"/api/interview-sessions/{sid}", headers=auth(world.user)).status_code == 204
    agent.answer(ANSWER)
    assert agent.responses[-1].status_code == 404 and agent.responses[-1].json()["code"] == "INTERVIEW_NOT_FOUND"


def test_after_the_seeker_ends_the_session_a_turn_is_refused_and_the_agents_end_is_already_ended(api, db, world, sid, clock):
    agent = HttpAgent(db, api, sid, clock)
    agent.start()
    assert api.post(f"/api/interview-sessions/{sid}/end", headers=auth(world.user)).status_code == 200
    agent.answer(ANSWER)
    refused = agent.responses[-1]
    assert refused.status_code == 409 and refused.json()["code"] == "INTERVIEW_NOT_ACTIVE"
    agent.engine.abort("candidate_left", 30.0)
    end = event(api, sid, end_body(agent.end_event()))
    assert end.status_code == 409 and end.json()["code"] == "INTERVIEW_ALREADY_ENDED"


@pytest.mark.parametrize(
    "body",
    [
        {"type": "turn"},
        {"type": "turn", "turn": {}, "coverage": {}},
        {"type": "end"},
        {"type": "end", "turn": {}, "coverage": {}},
    ],
    ids=["turn without a turn", "turn with a coverage", "end without a coverage", "end with a turn"],
)
def test_an_event_of_the_wrong_shape_is_refused_before_anything_is_written(api, db, sid, body):
    response = event(api, sid, body)
    assert response.status_code == 422 and no_store(response)
    assert response.json()["code"] in ("INTERVIEW_BAD_TURN", "INTERVIEW_BAD_COVERAGE")
    assert turn_rows(db, sid) == []


def test_a_string_where_the_service_wants_an_integer_is_not_coerced(api, db, sid, clock):
    agent = Agent(db, sid, clock)
    agent.engine.start()
    first = turn_body(agent.turn_events()[0])
    first["turn"]["seq"] = "1"
    response = event(api, sid, first)
    assert response.status_code == 422 and response.json() == {"code": "INTERVIEW_BAD_TURN", "message": "면접 이벤트가 올바르지 않습니다.", "field": "seq"}


@pytest.mark.parametrize("body", [{"type": "other"}, {"type": "turn", "turn": {"seq": 1, "secret_field": "답변"}}, {"type": "turn", "extra": "답변"}, [1, 2]])
def test_a_body_the_schema_refuses_is_a_sanitized_422(api, sid, body):
    response = event(api, sid, body)
    assert response.status_code == 422 and no_store(response)
    assert "답변" not in response.text and "secret_field" not in response.text
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])
