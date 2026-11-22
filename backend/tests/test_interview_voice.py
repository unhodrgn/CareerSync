"""The voice stage against the real application (M5 S4; docs/DECISIONS.md D54, D79, D80): the conversation rules and the join contract.

The real `VoiceController` and the real `InterviewRunner` run in-process against the application (`httpx.ASGITransport`), on the SQLite test
database and the test clock; only the voice is a fake (`say` and `interrupt`). No LiveKit, no network, no model. What the agent's own suite
shows with fakes (interview_agent/tests/test_controller.py) is shown here with the backend's real answers: a line is stored before it is spoken,
a nudge is stored, a deletion, the seeker's End and a consent withdrawal stop the controller, a departure posts the aborted end. The last tests
are the contract between the token the backend signs and the agent that reads it."""
import ast
import asyncio
import json

import pytest

from app.core import agent_auth
from app.core.config import REPO_ROOT, settings
from app.models import InterviewSession
from app.services import consent_service
from interview_agent.backend_client import ROOM_HEADER, SessionClient
from interview_agent.config import DEFAULT_AGENT_NAME
from interview_agent.controller import GREETING, VoiceController
from interview_agent.rooms import room_name, session_id_from_metadata

from .conftest import auth
from .interview_fixtures import Clock, build_world, new_session, turn_rows
from .test_interview_agent_runner import ANSWER, DATA, drive, make_runner, secret, wired, world  # noqa: F401 (the fixtures and helpers)
from .test_interview_api_join import AGENT_SECRET, KEY, LIVEKIT_URL, SECRET, claims, join
from .test_interview_api_session_common import api  # noqa: F401 (the fixture)
from .test_interview_internal_api import SECRET as AGENT_SECRET_VALUE


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


class Voice:
    """`say` and `interrupt` of the worker. Every line is checked against the stored transcript at the moment it is spoken."""

    def __init__(self, db, sid, check_stored=True):
        self.db, self.sid, self.check_stored = db, sid, check_stored
        self.spoken, self.interrupts, self.stored_when_spoken = [], 0, []

    async def say(self, text):
        stored = [r.text for r in turn_rows(self.db, self.sid)]
        self.spoken.append(text)
        self.stored_when_spoken.append(text in stored)
        return True

    def interrupt(self):
        self.interrupts += 1


async def build(http, db, sid, clock, **kw):
    """The worker opens the runner (reads the context) before the controller starts: nothing is spoken for a session that cannot run."""
    runner = make_runner(http, sid, clock)
    await runner.open()
    start = clock.now
    seconds = lambda: (clock.now - start).total_seconds()  # noqa: E731  (the controller's clock follows the backend's test clock too)
    voice = Voice(db, sid)
    controller = VoiceController(runner, say=voice.say, interrupt=voice.interrupt, clock=seconds, status_poll_seconds=5.0, **kw)
    return controller, runner, voice


async def settle(controller):
    while controller._tasks:
        await asyncio.gather(*list(controller._tasks), return_exceptions=True)


async def converse(controller, clock, answers=40, text=ANSWER):
    await controller.run_opening()
    while not controller.done.is_set() and answers:
        clock.advance(20)
        assert controller.submit(text) is True
        await settle(controller)
        answers -= 1


def status(db, sid):
    db.expire_all()
    row = db.get(InterviewSession, sid)
    return row.status, row.end_reason


# ── A whole interview, spoken ──


def test_a_whole_spoken_interview_stores_each_line_before_it_is_spoken_and_ends_completed(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await converse(controller, clock)
        return controller, voice

    controller, voice = drive(go)
    assert controller.outcome == "completed" and status(db, sid) == ("completed", "plan_exhausted")
    assert voice.spoken[0] == GREETING and "AI" in GREETING
    rows = turn_rows(db, sid)
    assert [r.text for r in rows if r.role == "agent"] == voice.spoken[1:], "everything the interviewer said, and nothing else, is in the transcript"
    assert GREETING not in [r.text for r in rows], "the greeting is a fixed disclosure, not one of the engine's turns"
    assert all(voice.stored_when_spoken[1:]), "store, then speak: every line was already stored when it was spoken"
    assert rows[0].seq == 1 and rows[0].kind == "question" and rows[-1].kind == "closing" and voice.spoken[-1] == rows[-1].text


def test_the_end_of_the_budget_is_found_by_the_silence_tick_with_no_answer_at_all(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        clock.advance(settings.INTERVIEW_MAX_SECONDS - 30)  # inside the engine's wrap-up reserve, before the backend's deadline
        await controller.tick()
        return controller, voice

    controller, voice = drive(go)
    assert controller.outcome == "completed" and status(db, sid) == ("completed", "time")
    assert voice.spoken[-1] == turn_rows(db, sid)[-1].text


# ── Silence ──


def test_a_silent_candidate_is_nudged_with_a_stored_line_and_nothing_is_said_before_the_time(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        spoken_after_opening = len(voice.spoken)
        clock.advance(settings.INTERVIEW_SILENCE_NUDGE_SECONDS - 1)
        await controller.tick()
        assert len(voice.spoken) == spoken_after_opening
        clock.advance(2)
        await controller.tick()
        return controller, voice

    controller, voice = drive(go)
    rows = turn_rows(db, sid)
    assert [r.kind for r in rows] == ["question", "nudge"] and voice.spoken[-1] == rows[-1].text and all(voice.stored_when_spoken[1:])
    assert not controller.done.is_set()


def test_while_the_candidate_is_speaking_no_silence_is_counted(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        controller.set_candidate_speaking(True)
        clock.advance(settings.INTERVIEW_SILENCE_SKIP_SECONDS * 2)
        await controller.tick()
        return voice

    voice = drive(go)
    assert [r.kind for r in turn_rows(db, sid)] == ["question"] and len(voice.spoken) == 2


# ── Stopping ──


def test_the_seeker_deleting_the_session_stops_the_controller_within_one_poll_and_nothing_more_is_posted(wired, db, world, sid, clock):
    from fastapi.testclient import TestClient

    from app.main import app

    seeker = TestClient(app, raise_server_exceptions=False)

    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        assert seeker.delete(f"/api/interview-sessions/{sid}", headers=auth(world.user)).status_code == 204
        clock.advance(4)
        await controller.tick()
        assert not controller.done.is_set()  # not polled yet
        clock.advance(2)
        await controller.tick()
        return controller, voice

    controller, voice = drive(go)
    assert controller.outcome == "gone" and voice.interrupts == 1
    assert db.query(InterviewSession).count() == 0


def test_the_seekers_end_and_a_consent_withdrawal_each_stop_the_controller_and_say_why(wired, db, world, sid, clock):
    from fastapi.testclient import TestClient

    from app.main import app

    async def ended(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        assert TestClient(app).post(f"/api/interview-sessions/{sid}/end", headers=auth(world.user)).status_code == 200
        clock.advance(6)
        await controller.tick()
        return controller

    assert drive(ended).outcome == "ended_elsewhere"
    other = build_world(db, email="two@interview.test")
    other_sid = new_session(db, other, clock)

    async def withdrawn(http):
        controller, runner, voice = await build(http, db, other_sid, clock)
        await controller.run_opening()
        consent_service.withdraw_ai(db, other.user, now=clock.now)
        clock.advance(6)
        await controller.tick()
        return controller, voice

    controller, voice = drive(withdrawn)
    assert controller.outcome == "consent_withdrawn" and voice.interrupts == 1
    assert status(db, other_sid) == ("aborted", "consent_withdrawn") and [r.kind for r in turn_rows(db, other_sid)] == ["question"]


def test_the_candidate_leaving_posts_the_aborted_end_with_no_closing_line_and_speaks_nothing(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        spoken = len(voice.spoken)
        await controller.candidate_left()
        return controller, voice, spoken

    controller, voice, spoken = drive(go)
    assert controller.outcome == "aborted" and status(db, sid) == ("aborted", "candidate_left")
    assert len(voice.spoken) == spoken and "closing" not in [r.kind for r in turn_rows(db, sid)]


def test_a_closed_transport_is_stored_as_session_closed(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        await controller.candidate_left("session_closed:participant_removed")

    drive(go)
    assert status(db, sid) == ("aborted", "session_closed")  # the part before the colon: a free-form reason is never stored


def test_an_answer_that_arrives_while_one_is_being_handled_is_not_stored(wired, db, sid, clock):
    async def go(http):
        controller, runner, voice = await build(http, db, sid, clock)
        await controller.run_opening()
        runner.answer_delay = 0  # the real runner has none: the first answer is simply still being handled when the second arrives
        clock.advance(20)
        assert controller.submit(ANSWER) is True
        assert controller.submit("겹쳐 말한 다른 답변입니다.") is False
        await settle(controller)
        return controller

    controller = drive(go)
    texts = [r.text for r in turn_rows(db, sid) if r.role == "candidate"]
    assert len(texts) == 1 and controller.dropped_turns == 1 and all("겹쳐" not in t for t in texts)


# ── The contract between the token and the agent ──


def test_the_agent_name_the_backend_dispatches_is_the_one_the_agent_registers_under():
    tree = ast.parse((REPO_ROOT / "backend" / "app" / "core" / "config.py").read_text(encoding="utf-8"))
    defaults = [
        node.value.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "INTERVIEW_AGENT_NAME"
    ]
    assert defaults == [DEFAULT_AGENT_NAME] == ["careersync-interviewer"]


def test_the_token_the_backend_signs_names_a_room_and_a_session_that_the_agent_reads_back(api, db, clock, monkeypatch):
    from app.models.interview import InterviewStatus as S

    from .test_interview_history_active import add

    world = build_world(db)
    session_id = add(db, world, clock, S.CREATED, deadline=300)
    monkeypatch.setattr(settings, "LIVEKIT_URL", LIVEKIT_URL)
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", KEY)
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", SECRET)
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", AGENT_SECRET)
    body = join(api, session_id, world.user).json()
    (dispatch,) = claims(body["token"]).room_config.agents
    assert session_id_from_metadata(dispatch.metadata) == session_id, "the agent finds the session in the metadata the token carries"
    assert body["room"] == room_name(session_id, AGENT_SECRET) == agent_auth.room_name(session_id, AGENT_SECRET)
    assert dispatch.agent_name == DEFAULT_AGENT_NAME


def test_a_console_job_derives_the_same_room_from_the_secret(wired, db, world, sid, clock):
    """In `console` mode there is no room: the client derives it from the agent secret, and the backend accepts it."""
    async def go(http):
        client = SessionClient(http, AGENT_SECRET_VALUE, sid)
        assert client.headers[ROOM_HEADER] == agent_auth.room_name(sid, AGENT_SECRET_VALUE)
        return await client.context()

    assert drive(go)["status"] == "created"
