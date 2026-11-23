"""The Interview Agent's runner against the real application (M5 S2; docs/DECISIONS.md D54, D80).

`interview_agent.runner.InterviewRunner` and its `SessionClient` talk to the app in-process (`httpx.ASGITransport`), on the SQLite test
database and the test clock, so every rule of the internal API and the ingestion applies for real. No model, no network, no LiveKit: the
model is a fake with the `LLMClient` shape, called through `ai.interview.boundary.ask` as the agent calls Groq. The agent's own unit tests
(the client's error sorting, the Groq adapter, the settings) run in the agent's environment (interview_agent/tests)."""
import asyncio
import json
import time

import httpx
import pytest

from app.api.v1.interview_sessions import get_clock
from app.core import agent_auth
from app.core.config import REPO_ROOT, settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewSession
from app.services import consent_service
from interview_agent.backend_client import SessionClient
from interview_agent.runner import InterviewRunner, Stopped

from .conftest import auth
from .interview_fixtures import Clock, build_world, new_session, turn_rows
from .test_interview_internal_api import SECRET

ANSWER = "Java와 Spring Boot로 주문 API를 만들고 트랜잭션 경계를 정리했습니다. 테스트 커버리지도 높였습니다."
DATA = REPO_ROOT / "data"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", SECRET)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def wired(db, clock):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock
    yield
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


class FlakyTransport(httpx.AsyncBaseTransport):
    """The app, behind a transport that can answer chosen requests with a 503 before they reach it."""

    def __init__(self, fail=lambda request, body: False):
        self.inner = httpx.ASGITransport(app=app)
        self.fail = fail
        self.failed = 0

    async def handle_async_request(self, request):
        body = json.loads(request.content) if request.content else None
        if self.fail(request, body):
            self.failed += 1
            return httpx.Response(503, json={"code": "unavailable"})
        return await self.inner.handle_async_request(request)


def make_runner(http, session_id, clock, *, model=None, room=None, timeout=3.0):
    start = clock.now
    seconds = lambda: (clock.now - start).total_seconds()  # noqa: E731  (the runner's clock follows the backend's test clock)
    client = SessionClient(http, SECRET, session_id, room=room, delays=(0.0, 0.0))
    return InterviewRunner(client, data_dir=DATA, model=model, llm_timeout=timeout, clock=seconds)


def drive(coro_factory, transport=None):
    async def main():
        async with httpx.AsyncClient(transport=transport or httpx.ASGITransport(app=app), base_url="http://test") as http:
            return await coro_factory(http)

    return asyncio.run(main())


async def interview(runner, clock, answers=40, text=ANSWER):
    await runner.open()
    spoken = list(await runner.start())
    while not runner.finished and answers:
        clock.advance(20)
        spoken += await runner.answer(text)
        answers -= 1
    return spoken


# ── A whole interview ──


def test_a_whole_interview_in_rules_mode_completes_with_one_end_event_and_its_feedback_works(api_seeker, db, world, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        spoken = await interview(runner, clock)
        return runner, spoken

    runner, spoken = drive(go)
    assert runner.stopped == "completed"
    rows = turn_rows(db, sid)
    assert rows[0].seq == 1 and rows[0].kind == "question" and rows[-1].kind == "closing"
    assert [r.text for r in rows if r.role == "agent"] == spoken  # every spoken line was stored first, in order, and nothing else was spoken
    session = db.get(InterviewSession, sid)
    db.refresh(session)
    assert session.status == "completed"
    feedback = api_seeker.post(f"/api/interview-sessions/{sid}/feedback", headers=auth(world.user))
    assert feedback.status_code == 200 and feedback.json()["final"] is True


def test_the_seekers_name_is_masked_before_anything_is_posted(wired, db, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        clock.advance(20)
        await runner.answer("저는 김민준입니다. " + ANSWER)

    drive(go)
    assert all("김민준" not in row.text for row in turn_rows(db, sid))


# ── Stopping ──


def test_a_deletion_mid_interview_stops_the_runner_and_nothing_more_is_posted(api_seeker, db, world, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        assert api_seeker.delete(f"/api/interview-sessions/{sid}", headers=auth(world.user)).status_code == 204
        with pytest.raises(Stopped) as by_poll:
            await runner.check()
        assert by_poll.value.reason == "gone"
        with pytest.raises(Stopped):
            await runner.answer(ANSWER)  # a stopped runner refuses before it posts anything
        return runner

    runner = drive(go)
    assert runner.stopped == "gone" and turn_rows(db, sid) == []


def test_a_deletion_is_also_noticed_on_the_next_post(api_seeker, db, world, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        api_seeker.delete(f"/api/interview-sessions/{sid}", headers=auth(world.user))
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return stop.value.reason

    assert drive(go) == "gone"


def test_the_seekers_end_stops_the_runner_without_an_agent_end_event(api_seeker, db, world, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        assert api_seeker.post(f"/api/interview-sessions/{sid}/end", headers=auth(world.user)).status_code == 200
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return stop.value.reason

    assert drive(go) == "ended_elsewhere"
    session = db.get(InterviewSession, sid)
    db.refresh(session)
    assert session.end_reason == "seeker_ended" and [r.kind for r in turn_rows(db, sid)] == ["question"]


def test_the_candidate_leaving_posts_one_aborted_end_without_a_closing_line(wired, db, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        clock.advance(20)
        await runner.answer(ANSWER)
        await runner.leave("candidate_left")
        return runner

    runner = drive(go)
    session = db.get(InterviewSession, sid)
    db.refresh(session)
    assert runner.stopped == "aborted" and session.status == "aborted" and session.end_reason == "candidate_left"
    assert "closing" not in [r.kind for r in turn_rows(db, sid)]


def test_leaving_before_the_first_question_posts_nothing(wired, db, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.leave("candidate_left")
        return runner

    assert drive(go).stopped == "candidate_left"
    assert turn_rows(db, sid) == [] and db.get(InterviewSession, sid).status == "created"


def test_time_running_out_ends_the_interview_with_the_reason_time(wired, db, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        clock.advance(settings.INTERVIEW_MAX_SECONDS - 30)  # inside the engine's wrap-up reserve, before the backend's deadline
        spoken = await runner.answer(ANSWER)
        return runner, spoken

    runner, spoken = drive(go)
    session = db.get(InterviewSession, sid)
    db.refresh(session)
    assert runner.stopped == "completed" and session.status == "completed" and session.end_reason == "time"
    assert spoken[-1] == turn_rows(db, sid)[-1].text


def test_a_session_that_is_not_joinable_or_another_room_does_not_start(api_seeker, db, world, sid, clock):
    async def wrong_room(http):
        runner = make_runner(http, sid, clock, room=agent_auth.room_name(sid + 1, SECRET))
        with pytest.raises(Stopped) as stop:
            await runner.open()
        return stop.value.reason

    assert drive(wrong_room) == "gone"
    api_seeker.post(f"/api/interview-sessions/{sid}/end", headers=auth(world.user))

    async def ended(http):
        runner = make_runner(http, sid, clock)
        with pytest.raises(Stopped) as stop:
            await runner.open()
        return stop.value.reason

    assert drive(ended) == "not_joinable"


def test_a_permanent_refusal_aborts_the_session_with_agent_error(wired, db, sid, clock):
    """The candidate's answer is stored, then the interviewer's next line is refused (a NUL in it): the runner posts the aborted end."""

    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        original = runner.client.post_event

        async def corrupt(body):
            if body["type"] == "turn" and body["turn"]["role"] == "agent" and body["turn"]["seq"] > 1:
                body = {**body, "turn": {**body["turn"], "text": body["turn"]["text"] + "\x00"}}
            return await original(body)

        runner.client.post_event = corrupt
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return stop.value.reason

    assert drive(go) == "refused"
    session = db.get(InterviewSession, sid)
    db.refresh(session)
    assert session.status == "aborted" and session.end_reason == "agent_error"


def test_a_transient_failure_of_the_end_is_retried_and_stored_once(wired, db, sid, clock):
    failures = {"left": 1}

    def fail(request, body):
        if body and body.get("type") == "end" and failures["left"]:
            failures["left"] -= 1
            return True
        return False

    transport = FlakyTransport(fail)

    async def go(http):
        runner = make_runner(http, sid, clock)
        return runner, await interview(runner, clock)

    runner, _ = drive(go, transport)
    assert transport.failed == 1 and runner.stopped == "completed"
    assert [r.kind for r in turn_rows(db, sid)].count("closing") == 1


# ── The model ──


class FakeModel:
    """The `LLMClient` shape the agent's Groq client has. Records what it is sent; answers with `reply(user)`."""

    model = "fake-groq"

    def __init__(self, reply=None, delay=0.0, error=None, on_call=None):
        self.reply, self.delay, self.error, self.on_call = reply, delay, error, on_call
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.calls.append((system, user))
        if self.on_call:  # runs inside the call, in the worker thread: something else happens while the model is being asked
            self.on_call()
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.reply(user) if self.reply else "{}"


def first_answer_method(db, sid):
    return next(r.method for r in turn_rows(db, sid) if r.role == "candidate")


def test_the_model_is_asked_through_ask_with_masked_text_only(wired, db, sid, clock):
    model = FakeModel()

    async def go(http):
        runner = make_runner(http, sid, clock, model=model)
        await runner.open()
        await runner.start()
        clock.advance(20)
        await runner.answer("제 이름은 김민준이고 전화번호는 010-1234-5678입니다. " + ANSWER)

    drive(go)
    assert len(model.calls) == 1
    system, user = model.calls[0]
    assert "김민준" not in user and "1234-5678" not in user and "트랜잭션" in user
    assert first_answer_method(db, sid) == "rules"  # "{}" is not a valid analysis: the rules decided (D54)


@pytest.mark.parametrize("model", [FakeModel(delay=0.5), FakeModel(error=RuntimeError("down"))], ids=["timeout", "error"])
def test_a_slow_or_failing_model_means_the_rules_at_once(wired, db, sid, clock, model):
    async def go(http):
        runner = make_runner(http, sid, clock, model=model, timeout=0.1)
        await runner.open()
        await runner.start()
        clock.advance(20)
        started = time.perf_counter()
        await runner.answer(ANSWER)
        return runner, time.perf_counter() - started

    runner, took = drive(go)
    assert first_answer_method(db, sid) == "rules"
    assert runner.timings[0][0] in ("timeout", "error:RuntimeError")
    assert took < 0.45, "the runner waits for the timeout, not for the model"


def test_the_timeout_never_exceeds_the_sessions_limit(wired, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock, timeout=30.0)
        await runner.open()
        return runner.llm_timeout

    assert drive(go) == float(settings.INTERVIEW_TURN_LLM_DEADLINE_SECONDS)


def test_a_valid_model_analysis_is_used_and_recorded_with_its_method(wired, db, sid, clock):
    model = FakeModel(reply=lambda user: None)

    async def go(http):
        runner = make_runner(http, sid, clock, model=model)
        await runner.open()
        await runner.start()
        item = runner.engine.state.current
        ids = [p.id for p in item.rubric]
        model.reply = lambda user: json.dumps({"answer_type": "answered", "points": [{"id": i, "level": "demonstrated"} for i in ids], "quotes": [], "follow_up": None})
        clock.advance(20)
        await runner.answer(ANSWER)
        return runner

    runner = drive(go)
    assert runner.timings[0][0] == "ok", runner.timings
    assert first_answer_method(db, sid) == "llm:fake-groq"


# ── Consent withdrawal (D81, Q39) ──


def withdraw_now(db, world, clock):
    consent_service.withdraw_ai(db, world.user, now=clock.now)


def valid_reply(runner):
    ids = [p.id for p in runner.engine.state.current.rubric]
    return lambda user: json.dumps({"answer_type": "answered", "points": [{"id": i, "level": "demonstrated"} for i in ids], "quotes": [], "follow_up": None})


def ended_row(db, sid):
    session = db.get(InterviewSession, sid)
    db.refresh(session)
    return session.status, session.end_reason


def test_a_withdrawal_before_the_model_call_stops_the_runner_and_no_model_is_asked(wired, db, world, sid, clock):
    model = FakeModel()

    async def go(http):
        runner = make_runner(http, sid, clock, model=model)
        await runner.open()
        await runner.start()
        withdraw_now(db, world, clock)
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return runner, stop.value.reason

    runner, reason = drive(go)
    assert reason == "consent_withdrawn" and runner.stopped == "consent_withdrawn"
    assert model.calls == [], "no new AI inference may start after the consent is withdrawn (D65 (5))"
    assert [r.kind for r in turn_rows(db, sid)] == ["question"]  # the answer was not processed or stored
    assert ended_row(db, sid) == ("aborted", "consent_withdrawn")


def test_a_model_call_that_started_before_the_withdrawal_is_refused_when_it_is_posted(wired, db, world, sid, clock):
    model = FakeModel(on_call=lambda: withdraw_now(db, world, clock))

    async def go(http):
        runner = make_runner(http, sid, clock, model=model)
        await runner.open()
        await runner.start()
        model.reply = valid_reply(runner)
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return runner, stop.value.reason

    runner, reason = drive(go)
    assert len(model.calls) == 1 and runner.timings[0][0] == "ok", "the call was already running, and finished"
    assert reason == "ended_elsewhere", "its result was refused by the backend, so the runner stops"
    assert [r.kind for r in turn_rows(db, sid)] == ["question"], "nothing of the answer or of the model's analysis was stored"
    assert ended_row(db, sid) == ("aborted", "consent_withdrawn")


def test_a_seeker_without_consent_whose_session_is_still_active_is_aborted_by_the_agent_with_no_model_call(wired, db, world, sid, clock):
    model = FakeModel()

    async def go(http):
        runner = make_runner(http, sid, clock, model=model)
        await runner.open()
        await runner.start()
        world.user.consent_ai_at = None  # the moment between two statements: the consent is gone, the session has not been ended yet
        db.commit()
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return runner, stop.value.reason

    runner, reason = drive(go)
    assert reason == "consent_withdrawn" and runner.stopped == "consent_withdrawn" and model.calls == []
    assert [r.kind for r in turn_rows(db, sid)] == ["question"]
    assert ended_row(db, sid) == ("aborted", "session_closed"), "the agent's own end: a free-form reason is never stored (the part before the colon)"


def test_the_rules_mode_needs_no_check_and_still_stops_on_the_refused_post(wired, db, world, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)  # no model
        await runner.open()
        await runner.start()
        withdraw_now(db, world, clock)
        clock.advance(20)
        with pytest.raises(Stopped) as stop:
            await runner.answer(ANSWER)
        return stop.value.reason

    assert drive(go) == "ended_elsewhere"
    assert [r.kind for r in turn_rows(db, sid)] == ["question"] and ended_row(db, sid) == ("aborted", "consent_withdrawn")


def test_the_status_check_names_the_withdrawal(wired, db, world, sid, clock):
    async def go(http):
        runner = make_runner(http, sid, clock)
        await runner.open()
        await runner.start()
        assert (await runner.check())["ai_consent"] is True
        withdraw_now(db, world, clock)
        with pytest.raises(Stopped) as stop:
            await runner.check()
        return stop.value.reason

    assert drive(go) == "consent_withdrawn"


def test_a_context_that_cannot_be_read_means_no_model_call_and_the_rules_decide(wired, db, sid, clock):
    down = {"on": False}
    transport = FlakyTransport(lambda request, body: down["on"] and request.method == "GET")
    model = FakeModel()

    async def go(http):
        runner = make_runner(http, sid, clock, model=model)
        await runner.open()
        await runner.start()
        down["on"] = True  # from now on the context cannot be read; the events still go through
        clock.advance(20)
        await runner.answer(ANSWER)
        return runner

    runner = drive(go, transport)
    assert model.calls == [] and not runner.finished and transport.failed == 1, "one attempt, no retry delay"
    assert first_answer_method(db, sid) == "rules"


@pytest.fixture
def api_seeker(wired):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=False)
