"""The Interview Agent's authentication helpers (M5 S1; docs/DECISIONS.md D80): the room name and the configured secret."""
import hashlib
import hmac

import pytest

from app.core import agent_auth
from app.core.config import settings
from app.core.errors import AppError

SECRET = "s" * 40


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", SECRET)
    return SECRET


def test_the_room_name_is_the_hmac_of_the_session_id_under_the_secret():
    expected = "cs-iv-" + hmac.new(SECRET.encode(), b"42", hashlib.sha256).hexdigest()
    assert agent_auth.room_name(42, SECRET) == expected
    assert agent_auth.room_name(42, SECRET) != agent_auth.room_name(43, SECRET)
    assert agent_auth.room_name(42, SECRET) != agent_auth.room_name(42, SECRET + "x")


def test_the_agent_package_computes_the_same_room_name():
    from interview_agent.rooms import room_name  # the agent cannot import the backend, so the formula is written twice (D56)

    for session_id in (1, 7, 2**31 - 1):
        assert room_name(session_id, SECRET) == agent_auth.room_name(session_id, SECRET)


@pytest.mark.parametrize("value", ["", "x" * 31, " " * 10])
def test_a_missing_or_short_secret_is_not_configured(monkeypatch, value):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", value)
    assert agent_auth.configured_secret() is None
    with pytest.raises(AppError) as refused:
        agent_auth.authenticated_room(secret=value, room="r")
    assert refused.value.status_code == 401 and refused.value.code == "AGENT_UNAUTHORIZED"


def test_a_secret_of_the_minimum_length_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", "y" * settings.INTERVIEW_AGENT_SECRET_MIN_CHARS)
    assert agent_auth.configured_secret() == "y" * settings.INTERVIEW_AGENT_SECRET_MIN_CHARS


@pytest.mark.parametrize("given", [None, "", SECRET[:-1], SECRET + "x", SECRET.upper(), "비밀" * 20])
def test_a_wrong_secret_is_401(secret, given):
    with pytest.raises(AppError) as refused:
        agent_auth.authenticated_room(secret=given, room="r")
    assert refused.value.status_code == 401 and refused.value.extra == {}


def test_the_right_secret_returns_the_room_and_the_room_check_binds_it(secret):
    room = agent_auth.room_name(5, secret)
    assert agent_auth.authenticated_room(secret=secret, room=room) == room
    agent_auth.require_room(5, room)
    for wrong in ("", agent_auth.room_name(6, secret), room[:-1], room + "0"):
        with pytest.raises(AppError) as refused:
            agent_auth.require_room(5, wrong)
        assert refused.value.status_code == 404 and refused.value.code == "INTERVIEW_NOT_FOUND"


def test_the_comparisons_are_constant_time():
    source = (agent_auth.__file__ and open(agent_auth.__file__, encoding="utf-8").read())
    assert "hmac.compare_digest" in source and " == expected" not in source and "!= expected" not in source
