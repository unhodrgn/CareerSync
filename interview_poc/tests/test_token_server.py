"""Token claims and the local HTTP server (a real server on an ephemeral port; the LiveKit room API is faked)."""
import http.client
import json
import re
import threading

import jwt
import pytest

from config import AGENT_NAME, Settings
from token_server import ROOM_PATTERN, SessionGate, issue_token, make_server

SECRET = "x" * 48  # long enough for HS256
SETTINGS = Settings(livekit_url="wss://example.livekit.cloud", livekit_api_key="devkey", livekit_api_secret=SECRET, avatar_enabled=True)


def decode(token):
    return jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_aud": False})


def test_the_token_lets_the_browser_publish_a_microphone_and_nothing_else():
    issued = issue_token(SETTINGS)
    claims = decode(issued.token)
    video = claims["video"]
    assert video["roomJoin"] is True and video["room"] == issued.room
    assert video["canPublishSources"] == ["microphone"]  # LiveKit refuses a camera or screen track even if the page tried
    assert video.get("canPublishData", False) is False
    assert video["canSubscribe"] is True
    assert claims["exp"] - claims["nbf"] <= 600  # short-lived
    assert claims["iss"] == "devkey"


def test_the_token_carries_no_personal_data_and_no_secret():
    issued = issue_token(SETTINGS)
    claims = decode(issued.token)
    assert re.fullmatch(r"candidate-[0-9a-f]{12}", issued.identity) and claims["sub"] == issued.identity
    assert claims["name"] == "Candidate"
    assert ROOM_PATTERN.match(issued.room)
    assert SECRET not in json.dumps(claims) and SECRET not in issued.token


def test_the_token_dispatches_the_poc_agent_into_a_small_room():
    config = decode(issue_token(SETTINGS).token)["roomConfig"]
    assert config["agents"][0]["agentName"] == AGENT_NAME
    assert config["maxParticipants"] == 3  # candidate, agent, avatar worker


def test_every_token_is_for_a_new_room():
    assert issue_token(SETTINGS).room != issue_token(SETTINGS).room


def test_session_gate_allows_one_session_at_a_time():
    now = [100.0]
    gate = SessionGate(window=190, clock=lambda: now[0])
    assert gate.acquire() is True and gate.acquire() is False
    gate.release()
    assert gate.acquire() is True
    now[0] += 191
    assert gate.acquire() is True  # a forgotten slot frees itself


# ── HTTP ──


@pytest.fixture
def server():
    deleted = []

    async def fake_delete(settings, room):
        deleted.append(room)

    httpd = make_server(SETTINGS, 0, delete_room=fake_delete)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], deleted
    finally:
        httpd.shutdown()
        httpd.server_close()


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response, data


def test_token_endpoint_and_one_session_at_a_time(server):
    port, _ = server
    first, body = request(port, "POST", "/api/token", {})
    data = json.loads(body)
    assert first.status == 200 and set(data) == {"url", "token", "room", "identity", "max_seconds", "avatar"}
    assert data["url"] == SETTINGS.livekit_url and data["avatar"] is True and data["max_seconds"] <= 180
    assert SECRET.encode() not in body  # the signed token is handed out; the secret never is
    second, body2 = request(port, "POST", "/api/token", {})
    assert second.status == 409 and json.loads(body2)["code"] == "SESSION_BUSY"


def test_ending_a_session_deletes_its_room_and_frees_the_slot(server):
    port, deleted = server
    data = json.loads(request(port, "POST", "/api/token", {})[1])
    response, _ = request(port, "POST", "/api/end", {"room": data["room"]})
    assert response.status == 204 and deleted == [data["room"]]
    assert request(port, "POST", "/api/token", {})[0].status == 200


def test_end_ignores_room_names_that_are_not_ours(server):
    port, deleted = server
    for room in ("someone-elses-room", "poc-../../x", 123, None):
        assert request(port, "POST", "/api/end", {"room": room})[0].status == 204
    assert deleted == []


def test_static_page_is_served_and_nothing_else(server):
    port, _ = server
    page, body = request(port, "GET", "/")
    assert page.status == 200 and "AI 면접 연습" in body.decode("utf-8")
    assert page.getheader("X-Content-Type-Options") == "nosniff" and page.getheader("Cache-Control") == "no-store"
    for path in ("/../config.py", "/..%2Fconfig.py", "/.env", "/.hidden/x", "/missing", "/%2e%2e/.env"):
        assert request(port, "GET", path)[0].status == 404, path
    assert request(port, "POST", "/api/other", {})[0].status == 404
