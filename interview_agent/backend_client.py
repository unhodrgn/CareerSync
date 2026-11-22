"""The agent's client of the backend's internal API, for one session (M5 S2; docs/DECISIONS.md D58, D79).

Every call carries the shared secret and the session's room. Answers are sorted into what the runner has to do:

- `Gone`: 404. The session was deleted or expired, or the room is not the session's: stop, post nothing more.
- `Ended`: 409 `INTERVIEW_ALREADY_ENDED` or `INTERVIEW_NOT_ACTIVE`. The seeker ended it, or its time is over: stop, post nothing more.
- `SeqGap`: 409 `INTERVIEW_SEQ_GAP`, with the sequence number the backend expects.
- `Refused`: any other 4xx (a 422, `INTERVIEW_SEQ_CONFLICT`, a wrong secret): permanent; the runner aborts.
- `Transient`: no answer, a timeout or a 5xx, after the retries. Every request is retried with the same payload, which the backend treats
  as a duplicate, so a retry never stores an event twice.

Nothing here logs a request or a response body: they carry the masked transcript and the plan.
"""
import asyncio
import logging

import httpx

from interview_agent.rooms import room_name

log = logging.getLogger("interview_agent.backend")

SECRET_HEADER = "X-Interview-Agent-Secret"
ROOM_HEADER = "X-Interview-Agent-Room"
BASE = "/api/internal/interview-sessions"
RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0)  # about 7.5 s in all: well inside the backend's end grace (30 s)


class BackendError(Exception):
    def __init__(self, status: int | None, code: str, body: dict | None = None):
        super().__init__(f"{status} {code}")
        self.status, self.code, self.body = status, code, body or {}


class Gone(BackendError):
    pass


class Ended(BackendError):
    pass


class SeqGap(BackendError):
    @property
    def expected(self) -> int | None:
        value = self.body.get("expected_seq")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class Refused(BackendError):
    pass


class Transient(BackendError):
    pass


ENDED_CODES = frozenset({"INTERVIEW_ALREADY_ENDED", "INTERVIEW_NOT_ACTIVE"})


def classify(response: httpx.Response) -> BackendError | None:
    """None for a 2xx, else the error to raise."""
    if response.is_success:
        return None
    try:
        body = response.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    code = str(body.get("code") or f"http_{response.status_code}")
    status = response.status_code
    if status >= 500:
        return Transient(status, code, body)
    if status == 404:
        return Gone(status, code, body)
    if status == 409 and code in ENDED_CODES:
        return Ended(status, code, body)
    if status == 409 and code == "INTERVIEW_SEQ_GAP":
        return SeqGap(status, code, body)
    return Refused(status, code, body)


class SessionClient:
    """The internal API for one session. `room`: the LiveKit room the agent is in (voice), or None to derive it from the secret (the text
    driver, which has no room)."""

    def __init__(self, http: httpx.AsyncClient, secret: str, session_id: int, *, room: str | None = None, delays=RETRY_DELAYS):
        self.http, self.session_id, self.delays = http, session_id, tuple(delays)
        self.headers = {SECRET_HEADER: secret, ROOM_HEADER: room if room is not None else room_name(session_id, secret)}

    async def context(self) -> dict:
        return await self._request("GET", f"{BASE}/{self.session_id}/context")

    async def post_event(self, body: dict) -> dict:
        return await self._request("POST", f"{BASE}/{self.session_id}/events", json=body)

    async def _request(self, method: str, path: str, **kw) -> dict:
        last: BackendError | None = None
        for attempt, delay in enumerate((0.0, *self.delays)):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await self.http.request(method, path, headers=self.headers, **kw)
            except httpx.HTTPError as e:  # no answer: connection refused, reset, timeout
                last = Transient(None, type(e).__name__)
            else:
                error = classify(response)
                if error is None:
                    return response.json()
                if not isinstance(error, Transient):
                    raise error
                last = error
            log.warning("backend call failed (%s, attempt %d); retrying with the same payload", last.code, attempt + 1)
        assert last is not None
        raise last
