import asyncio

import httpx
import pytest

from interview_agent.backend_client import ROOM_HEADER, SECRET_HEADER, Ended, Gone, Refused, SeqGap, SessionClient, Transient
from interview_agent.rooms import room_name

SECRET = "q" * 40


def run(coro_factory, handler, **kw):
    async def main():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://backend") as http:
            return await coro_factory(SessionClient(http, SECRET, 7, delays=(0.0, 0.0), **kw))

    return asyncio.run(main())


def test_every_call_carries_the_secret_and_the_sessions_room():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    assert run(lambda c: c.context(), handler) == {"ok": True}
    assert seen[0].url.path == "/api/internal/interview-sessions/7/context"
    assert seen[0].headers[SECRET_HEADER] == SECRET and seen[0].headers[ROOM_HEADER] == room_name(7, SECRET)
    run(lambda c: c.post_event({"type": "turn"}), handler, room="cs-iv-given")
    assert seen[-1].headers[ROOM_HEADER] == "cs-iv-given" and seen[-1].method == "POST"


@pytest.mark.parametrize(
    "status, body, error",
    [
        (404, {"code": "INTERVIEW_NOT_FOUND"}, Gone),
        (409, {"code": "INTERVIEW_ALREADY_ENDED"}, Ended),
        (409, {"code": "INTERVIEW_NOT_ACTIVE", "status": "aborted"}, Ended),
        (409, {"code": "INTERVIEW_SEQ_GAP", "expected_seq": 4}, SeqGap),
        (409, {"code": "INTERVIEW_SEQ_CONFLICT"}, Refused),
        (422, {"code": "INTERVIEW_BAD_TURN", "field": "text"}, Refused),
        (401, {"code": "AGENT_UNAUTHORIZED"}, Refused),
    ],
)
def test_answers_are_sorted_into_what_the_runner_does(status, body, error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    with pytest.raises(error) as raised:
        run(lambda c: c.post_event({"type": "turn"}), handler)
    assert raised.value.code == body["code"] and len(calls) == 1  # never retried
    if error is SeqGap:
        assert raised.value.expected == 4


def test_a_5xx_or_no_answer_is_retried_with_the_same_payload_then_transient():
    bodies = []

    def handler(request):
        bodies.append(request.content)
        if len(bodies) == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(503, text="busy")

    with pytest.raises(Transient):
        run(lambda c: c.post_event({"type": "end", "coverage": {}}), handler)
    assert len(bodies) == 3 and len(set(bodies)) == 1


def test_a_retry_that_succeeds_returns_the_answer():
    count = {"n": 0}

    def handler(request):
        count["n"] += 1
        return httpx.Response(502) if count["n"] == 1 else httpx.Response(200, json={"outcome": "duplicate"})

    assert run(lambda c: c.post_event({"type": "turn"}), handler) == {"outcome": "duplicate"}


def test_a_context_read_without_retry_makes_one_attempt_and_the_default_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(Transient):
        run(lambda c: c.context(retry=False), handler)
    assert len(calls) == 1  # the status poll and the check before a model call never hold a turn for the retry delays
    calls.clear()
    with pytest.raises(Transient):
        run(lambda c: c.context(), handler)
    assert len(calls) == 3  # the first attempt and the two retries of `run` (delays=(0.0, 0.0))
