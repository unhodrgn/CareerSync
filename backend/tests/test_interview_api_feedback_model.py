"""`POST /api/interview-sessions/{session_id}/feedback`, Gate B: the outcomes that ask a model (M4 S4.5; docs/DECISIONS.md D63, D64, D65, D66, D67).

The route calls `interview_feedback_service.ensure`, so these tests drive every model-backed outcome of the S3b service through HTTP and show
what the client gets and what the database keeps: a usable model report stored once and never changed; the three attempts and the daily
quota; the busy lease with its `Retry-After`; a worker that lost its lease (the winner's stored report, or its own report as provisional); a
session deleted during the call; an unexpected error; and the transaction order: the model is called with no transaction open, after the lease,
the attempt and the reservation were committed together, and the report is stored afterwards by a statement that the lease token fences. The
model is the recording spy of the S3b tests: no network, no key. The races run on one SQLite connection with a second database session as "the
other request": they show the logic and prove nothing about parallel requests, which only the PostgreSQL tests of the service cover (skipped
without a database). The foundation (shapes, 401/403/404/422/405, the outcomes that need no model) is in test_interview_api_feedback.py."""
import re
from contextlib import contextmanager

import pytest
from sqlalchemy import event, select

from ai.interview import feedback as feedback_module
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewSession, InterviewTurn, User
from app.schemas.application import AI_NOTICE
from app.services import interview_feedback_service as fb
from app.services import interview_service as svc

from .conftest import auth
from .interview_feedback_fixtures import (
    USABLE,
    SpyLLM,
    askable_session,
    feedback_used,
    finished_session,
    install,
    other_session,
    row,
)
from .interview_fixtures import SAMPLE_CV, build_world
from .test_interview_api_feedback import NOT_EXPOSED, REPORT_KEYS, TOP_KEYS, at, ok, refused, roomy_sessions, sid, unchanged, world  # noqa: F401 (the fixtures)
from .test_interview_api_history import keys_of
from .test_interview_api_session_common import FEEDBACK, URL, api, clock, no_store, no_wall_clock  # noqa: F401 (the fixtures)

SECRET = "SECRET-MARKER-답변-내용"
CV_MARKER = "CV-MARKER-경력-이력서"
GOOD = "답변은 상황과 역할, 해결 과정과 결과의 순서로 구성해 보세요."
# What a feedback sentence must not say: a score, a rank, a verdict, a comparison, a claim about the company (D63 (4))
BAD_SENTENCES = ["종합 점수는 85점입니다.", "상위 10% 수준입니다.", "이 직무에 적합합니다.", "다른 지원자보다 잘했습니다.", "회사의 요구 사항을 먼저 알아보세요."]
LEASE = settings.INTERVIEW_FEEDBACK_LEASE_SECONDS


def reply_of(response) -> dict:
    """A 200 with exactly the approved fields, and nothing of the service's internals."""
    body = ok(response)
    assert set(body) == TOP_KEYS and body["notice"] == AI_NOTICE and set(body["report"]) == REPORT_KEYS
    assert not NOT_EXPOSED & keys_of(body) and not [key for key in keys_of(body) if "weight" in key.lower()]
    return body


def request(api, headers, session_id):
    return api.post(f"{URL}/{session_id}{FEEDBACK[2]}", headers=headers)


def columns(db, session_id):
    """(feedback stored?, method, attempts, lease token, lease end) as the row says now."""
    r = row(db, session_id)
    return r.feedback is not None, r.feedback_method, r.feedback_attempts, r.feedback_lease_token, r.feedback_lease_until


@contextmanager
def as_another_request(db):
    """Run the requests inside as another request: its own database session, for the dependency that gives one."""
    second = other_session(db)
    app.dependency_overrides[get_db] = lambda: second
    try:
        yield second
    finally:
        app.dependency_overrides[get_db] = lambda: db
        second.close()


def fenced_by_lease_token(sql: str) -> bool:
    """The WHERE clause compares the lease token column with a bound parameter: `= ?` in SQLite's text of the statement, `= %(name)s::VARCHAR` in
    PostgreSQL's. The SET list writes `feedback_lease_token=` without spaces, so only the comparison matches."""
    return re.search(r"\bfeedback_lease_token = (?:\?|%\()", sql) is not None


class Timeline:
    """What the engine saw, in order: begin, commit, rollback, every statement, and the marks that a test adds (the model call)."""

    def __init__(self, db):
        self.engine, self.events, self.open = db.get_bind(), [], False

    def _begin(self, conn):
        self.open = True
        self.events.append(("begin",))

    def _commit(self, conn):
        self.open = False
        self.events.append(("commit",))

    def _rollback(self, conn):
        self.open = False
        self.events.append(("rollback",))

    def _sql(self, conn, cursor, statement, params, context, many):
        self.events.append(("sql", " ".join(statement.split())))

    def __enter__(self):
        for name, handler in (("begin", self._begin), ("commit", self._commit), ("rollback", self._rollback), ("before_cursor_execute", self._sql)):
            event.listen(self.engine, name, handler)
        return self

    def __exit__(self, *exc):
        for name, handler in (("begin", self._begin), ("commit", self._commit), ("rollback", self._rollback), ("before_cursor_execute", self._sql)):
            event.remove(self.engine, name, handler)

    def mark(self, name, **info):
        self.events.append((name, info, self.open))

    def split(self, name):
        names = [e[0] for e in self.events]
        at_ = names.index(name)
        return self.events[:at_], self.events[at_], self.events[at_ + 1:]


# ── A usable model report: stored once, returned final, never changed ──


def test_a_usable_model_report_is_validated_stored_and_returned_as_final(api, db, world, clock, sid, monkeypatch):
    headers, token_seen = auth(world.user), []
    llm = SpyLLM(db, model="claude-test")

    def look(_llm):  # the lease token, read by another session while the model is being called: it must never reach the client
        second = other_session(db)
        try:
            token_seen.append(second.scalar(select(InterviewSession.feedback_lease_token).where(InterviewSession.id == sid)))
        finally:
            second.close()

    llm.on_call = look
    install(monkeypatch, llm)
    response = request(api, headers, sid)
    body = reply_of(response)
    assert (body["final"], body["limited"], body["reason"]) == (True, False, None) and at(body["generated_at"]) == clock.now
    assert body["report"]["method"] == "llm:claude-test" and body["report"]["improvements"] == USABLE["improvements"]  # what the pipeline kept of the reply
    stored = row(db, sid)
    assert body["report"] == stored.feedback  # the answer is the stored report, field for field
    assert (stored.feedback_method, stored.feedback_prompt_version, stored.feedback_attempts) == ("llm:claude-test", "v1", 1)
    assert (stored.feedback_lease_token, stored.feedback_lease_until) == (None, None)  # the lease is gone with the store
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1
    assert len(token_seen[0]) == 32 and token_seen[0] not in response.text  # the lease token was real, and is nowhere in the answer


def test_a_repeated_request_returns_the_stored_report_with_no_new_call_attempt_or_quota(api, db, world, clock, sid, monkeypatch):
    headers = auth(world.user)
    llm = SpyLLM(db, model="first")
    install(monkeypatch, llm)
    first = reply_of(request(api, headers, sid))
    stored = row(db, sid)
    stored_at = stored.feedback_at
    llm.reply = {"strengths": [], "gaps": [], "improvements": ["다른 문장으로 바뀐 답입니다."], "practice_questions": []}  # a different answer would show
    for _ in range(3):
        clock.advance(3600)
        again = reply_of(request(api, headers, sid))
        assert again == first  # the same report and the same `generated_at`: stored reports are immutable
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1
    after = row(db, sid)
    assert (after.feedback, after.feedback_at, after.feedback_attempts, after.feedback_method) == (first["report"], stored_at, 1, "llm:first")


def test_a_reply_that_is_valid_only_in_part_keeps_the_valid_part_and_nothing_of_the_rest(api, db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db, reply={"strengths": [], "gaps": [], "improvements": [GOOD, *BAD_SENTENCES], "practice_questions": []})
    install(monkeypatch, llm)
    body = reply_of(request(api, auth(world.user), sid))
    assert body["final"] and body["report"]["method"] == "llm:spy-llm" and body["report"]["improvements"] == [GOOD]  # each failing sentence dropped on its own
    blob = "\n".join(str(value) for value in (body["report"]["improvements"], body["report"]["notes"], [g["text"] for g in body["report"]["gaps"]]))
    assert not [sentence for sentence in BAD_SENTENCES if sentence in blob]
    for field in ("improvements", "notes"):  # no score, rank or verdict anywhere in the sentences of the report
        assert not [line for line in body["report"][field] if feedback_module._SCORE_LIKE.search(line)], field
    assert not [line for line in [g["text"] for g in body["report"]["gaps"]] + [s["text"] for s in body["report"]["strengths"]] if feedback_module._SCORE_LIKE.search(line)]


def test_the_quotes_of_a_model_strength_are_exact_and_a_made_up_one_is_dropped(api, db, world, clock, monkeypatch):
    real = "Java 트랜잭션 처리를 직접 설계했습니다"
    llm = SpyLLM(db, reply={
        "strengths": [{"topic_id": "c1", "text": "Java 트랜잭션 처리 경험을 직접 설계한 사례로 설명했습니다.", "quotes": [real, "지어낸 문장입니다 정말로 그렇습니다"]}],
        "gaps": [], "improvements": [GOOD], "practice_questions": [],
    })
    install(monkeypatch, llm)
    session_id = askable_session(db, world, clock)
    body = reply_of(request(api, auth(world.user), session_id))
    assert body["final"] and body["report"]["method"] == "llm:spy-llm"
    strengths = [s for s in body["report"]["strengths"] if s["topic_id"] == "c1"]
    assert strengths and strengths[0]["quotes"] == [real]  # the real quote, verbatim, and not the invented one
    lines = [t.text for t in db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == session_id, InterviewTurn.role == "candidate"))]
    assert all(any(quote in line for line in lines) for s in body["report"]["strengths"] for quote in s["quotes"])  # every quote is in a masked candidate line
    assert "지어낸 문장" not in str(body)


def test_no_raw_cv_prompt_or_lease_data_reaches_the_report_or_the_answer(api, db, clock, monkeypatch):
    seeker = build_world(db, email="cv@interview.test", masked_cv=SAMPLE_CV + "\n" + CV_MARKER)
    session_id = finished_session(db, seeker, clock)
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    response = request(api, auth(seeker.user), session_id)
    body = reply_of(response)
    assert len(llm.calls) == 1 and CV_MARKER not in response.text  # not in the answer
    assert not [call for call in llm.calls if CV_MARKER in call[0] or CV_MARKER in call[1]]  # and it never reached the model
    system, user = llm.calls[0][0], llm.calls[0][1]
    assert system[40:120] not in response.text and user[:80] not in response.text  # no prompt text in the answer
    assert body["report"]["rubric_notice"] == feedback_module.RUBRIC_NOTICE
    assert {topic["importance"] for topic in body["report"]["topics"]} <= {"core", "important", "general", None}  # a label, never a number
    assert re.search(r"[0-9a-f]{32}", response.text) is None  # nothing that looks like a lease token


# ── Invalid replies fall back; the three attempts; the quota ──


@pytest.mark.parametrize(
    "reply",
    [
        {"strengths": [], "gaps": [], "improvements": ["서울 본사의 요구 사항을 이해해 보세요."], "practice_questions": []},
        {"strengths": [], "gaps": [], "improvements": [BAD_SENTENCES[0]], "practice_questions": []},
        {"strengths": [], "gaps": [], "improvements": [BAD_SENTENCES[2]], "practice_questions": [], "verdict": []},
        {"strengths": [], "gaps": [], "improvements": [GOOD + "\x00"], "practice_questions": []},
    ],
    ids=["a sentence about the company", "a score", "a field that is not allowed", "a NUL character"],
)
def test_a_reply_with_nothing_usable_follows_the_failure_path_and_nothing_is_stored(api, db, world, clock, sid, monkeypatch, reply):
    llm = SpyLLM(db, reply=reply)
    install(monkeypatch, llm)
    body = reply_of(request(api, auth(world.user), sid))
    assert (body["final"], body["limited"], body["reason"], body["generated_at"]) == (False, False, fb.REASON_MODEL_FAILED, None)
    assert body["report"]["method"] == "rules" and len(llm.calls) == 1
    assert columns(db, sid) == (False, None, 1, None, None) and feedback_used(db, world, clock) == 1  # not stored, the lease is free, the attempt is spent


def test_three_failed_attempts_are_provisional_twice_then_the_rules_report_is_stored_and_a_fourth_call_never_happens(api, db, world, clock, sid, monkeypatch):
    headers = auth(world.user)
    llm = SpyLLM(db, fail=True)
    install(monkeypatch, llm)
    for attempt in (1, 2):
        body = reply_of(request(api, headers, sid))
        assert (body["final"], body["limited"], body["reason"], body["generated_at"]) == (False, False, fb.REASON_MODEL_FAILED, None), attempt
        assert body["report"]["method"] == "rules"
        assert columns(db, sid) == (False, None, attempt, None, None)  # not stored; the lease is free again, so the seeker can ask at once
        assert len(llm.calls) == attempt and feedback_used(db, world, clock) == attempt  # the attempt and the reservation stay spent
    assert feedback_used(db, world, clock) < settings.INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS  # the next attempt is still possible today
    third = reply_of(request(api, headers, sid))
    assert (third["final"], third["reason"], third["report"]["method"]) == (True, None, "rules") and at(third["generated_at"]) == clock.now
    stored = row(db, sid)
    assert (stored.feedback, stored.feedback_method, stored.feedback_prompt_version, stored.feedback_attempts) == (third["report"], "rules", "v1", 3)
    assert (stored.feedback_lease_token, stored.feedback_lease_until) == (None, None)
    assert len(llm.calls) == 3 and feedback_used(db, world, clock) == 3
    for _ in range(2):  # the report is final now: a fourth call is not made, whatever the model would say
        llm.fail = False
        assert reply_of(request(api, headers, sid)) == third
    assert len(llm.calls) == 3 and feedback_used(db, world, clock) == 3 and row(db, sid).feedback_attempts == 3


def test_the_daily_quota_is_shared_by_a_seekers_sessions_and_resets_on_the_next_day(api, db, world, clock, monkeypatch):
    headers = auth(world.user)
    sessions = [finished_session(db, world, clock) for _ in range(4)]
    llm = SpyLLM(db, fail=True)
    install(monkeypatch, llm)
    for session_id in sessions[:3]:
        assert reply_of(request(api, headers, session_id))["reason"] == fb.REASON_MODEL_FAILED
    assert feedback_used(db, world, clock) == 3 and len(llm.calls) == 3
    limited = reply_of(request(api, headers, sessions[3]))
    assert (limited["final"], limited["limited"], limited["reason"], limited["generated_at"]) == (False, True, fb.REASON_QUOTA, None)
    assert limited["report"]["method"] == "rules"
    unchanged(db, sessions[3])  # the lease and the attempt were rolled back with the refused reservation
    assert feedback_used(db, world, clock) == 3 and len(llm.calls) == 3  # no call, and nothing more was reserved
    llm.fail = False
    clock.advance(24 * 3600)  # the next KST day
    again = reply_of(request(api, headers, sessions[3]))
    assert (again["final"], again["limited"], again["report"]["method"]) == (True, False, "llm:spy-llm") and feedback_used(db, world, clock) == 1


def test_a_used_up_quota_gives_the_provisional_limited_report_every_time_and_stores_nothing(api, db, world, clock, sid, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 0)
    headers = auth(world.user)
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    first = reply_of(request(api, headers, sid))
    assert (first["final"], first["limited"], first["reason"]) == (False, True, fb.REASON_QUOTA) and first["report"]["method"] == "rules"
    assert reply_of(request(api, headers, sid))["report"] == first["report"]  # made again, not stored
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, sid)  # no attempt, no lease, no report
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 3)
    assert reply_of(request(api, headers, sid))["final"] is True  # and as soon as there is quota the model is asked once


# ── The busy lease ──


def test_a_request_while_a_worker_is_generating_gets_the_409_with_the_seconds_left_and_costs_nothing(api, db, world, clock, sid, monkeypatch):
    headers, seen = auth(world.user), []

    def another_request(llm):
        for later in (0, 45):
            clock.advance(later)
            with as_another_request(db):
                response = request(api, headers, sid)
            seen.append((response.status_code, response.headers.get("retry-after"), response.headers.get("cache-control"), response.json()))
        clock.advance(-45)

    llm = SpyLLM(db, on_call=another_request)
    install(monkeypatch, llm)
    first = reply_of(request(api, headers, sid))
    busy = [(status, retry, cache, body["code"], body["retry_after_seconds"], set(body)) for status, retry, cache, body in seen]
    assert busy == [(409, "120", "no-store", fb.BUSY, 120, {"code", "message", "retry_after_seconds"}), (409, "75", "no-store", fb.BUSY, 75, {"code", "message", "retry_after_seconds"})]
    assert first["final"] and len(llm.calls) == 1 and feedback_used(db, world, clock) == 1  # the busy requests asked no model and took no reservation
    assert columns(db, sid)[:3] == (True, "llm:spy-llm", 1)  # and A's own attempt is the only one


# ── A lease that is lost, and the token fence ──


def test_a_worker_that_lost_its_lease_returns_the_stored_report_of_the_winner_and_changes_nothing(api, db, world, clock, sid, monkeypatch):
    headers, uid = auth(world.user), world.user.id
    b_llm = SpyLLM(db, model="llm-b")

    def worker_b(llm):
        clock.advance(LEASE + 1)  # A's lease has run out
        second = other_session(db)
        try:
            taken = fb.ensure(second, second.get(User, uid), sid, clock=clock)
        finally:
            second.close()
        assert (taken.final, taken.method, taken.attempts_used) == (True, "llm:llm-b", 2)

    a_llm = SpyLLM(db, model="llm-a", on_call=worker_b)
    llms = iter([a_llm, b_llm])
    monkeypatch.setattr(fb.ai_runtime, "llm", lambda: next(llms))
    body = reply_of(request(api, headers, sid))
    assert not db.in_transaction()  # (before any read of ours: a read opens one)
    assert (body["final"], body["reason"], body["report"]["method"]) == (True, None, "llm:llm-b")  # the winner's report, not A's own
    stored = row(db, sid)
    assert body["report"] == stored.feedback and (stored.feedback_method, stored.feedback_attempts, stored.feedback_lease_token) == ("llm:llm-b", 2, None)
    assert len(a_llm.calls) == len(b_llm.calls) == 1 and feedback_used(db, world, clock) == 2  # both calls stay spent


def test_a_stale_worker_returns_its_own_report_as_provisional_while_the_winner_still_holds_the_lease(api, db, world, clock, sid, monkeypatch):
    headers, uid, held = auth(world.user), world.user.id, {}

    def worker_b_takes_over(llm):
        clock.advance(LEASE + 1)
        second = other_session(db)
        try:
            claim = fb._claim(second, sid, uid, clock())  # B's T1: B is in its own model call now
        finally:
            second.close()
        assert isinstance(claim, fb._Claimed) and claim.attempt == 2
        held["b"] = claim

    llm = SpyLLM(db, on_call=worker_b_takes_over)
    install(monkeypatch, llm)
    body = reply_of(request(api, headers, sid))
    assert (body["final"], body["limited"], body["reason"], body["generated_at"]) == (False, False, fb.REASON_LEASE_LOST, None)
    assert body["report"]["method"] == "llm:spy-llm" and body["report"]["improvements"] == USABLE["improvements"]  # its own report, whole
    assert not db.in_transaction()
    stored = row(db, sid)  # A changed nothing: B's lease, B's attempt, no report
    assert (stored.feedback, stored.feedback_lease_token, stored.feedback_attempts) == (None, held["b"].token, 2)
    assert feedback_used(db, world, clock) == 2  # A's reservation and B's are both spent
    # B can still finish: its token still fences the store, and the next request then returns B's report
    assert fb._store(db, sid, uid, fb.rules_feedback([], fb.plan_view_from(fb.InterviewPlan.from_dict(stored.plan), None)), clock(), token=held["b"].token)
    winner = reply_of(request(api, headers, sid))
    assert winner["final"] and winner["report"] == row(db, sid).feedback and winner["report"]["method"] == "rules"


def test_a_stale_worker_whose_model_failed_cannot_release_the_lease_of_the_worker_that_took_over(api, db, world, clock, sid, monkeypatch):
    headers, uid, held = auth(world.user), world.user.id, {}

    def worker_b_takes_over(llm):
        clock.advance(LEASE + 1)
        second = other_session(db)
        try:
            held["b"] = fb._claim(second, sid, uid, clock())
        finally:
            second.close()
        held["lease"] = row(db, sid).feedback_lease_until

    install(monkeypatch, SpyLLM(db, fail=True, on_call=worker_b_takes_over))  # A fails, wants to release, and the lease is not its own any more
    body = reply_of(request(api, headers, sid))
    assert not db.in_transaction()  # (before any read of ours: a read opens one)
    assert (body["final"], body["reason"]) == (False, fb.REASON_MODEL_FAILED)
    stored = row(db, sid)
    assert (stored.feedback_lease_token, stored.feedback_lease_until, stored.feedback_attempts, stored.feedback) == (held["b"].token, held["lease"], 2, None)


def test_a_slow_worker_that_nobody_replaced_can_still_store_after_its_lease_ran_out(api, db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db, on_call=lambda _llm: clock.advance(LEASE + 30))
    install(monkeypatch, llm)
    body = reply_of(request(api, auth(world.user), sid))
    assert (body["final"], body["report"]["method"]) == (True, "llm:spy-llm") and row(db, sid).feedback_attempts == 1  # the fence is the token, not the clock
    assert feedback_used(db, world, clock) == 1


# ── A session deleted during the call; an unexpected error ──


def test_a_session_deleted_during_generation_is_a_404_the_report_is_dropped_and_the_reservation_stays_spent(api, db, world, clock, sid, monkeypatch):
    headers, uid = auth(world.user), world.user.id

    def delete_it(llm):
        second = other_session(db)
        try:
            svc.delete(second, second.get(User, uid), sid, clock=clock)
        finally:
            second.close()

    llm = SpyLLM(db, on_call=delete_it)
    install(monkeypatch, llm)
    response = request(api, headers, sid)
    body = refused(response, 404, svc.NOT_FOUND)
    assert set(body) == {"code", "message"} and "report" not in body
    db.rollback()
    assert db.get(InterviewSession, sid) is None  # the report was not stored anywhere: no row, so no orphan feedback
    assert db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == sid)).first() is None
    assert db.scalar(select(InterviewSession.id).where(InterviewSession.feedback.is_not(None))) is None
    assert feedback_used(db, world, clock) == 1 and len(llm.calls) == 1  # the ledger has no link to a session: nothing was given back


def test_an_unexpected_error_after_the_reservation_is_a_sanitized_500_that_frees_the_lease_and_keeps_the_attempt(api, db, world, clock, sid, monkeypatch):
    install(monkeypatch, SpyLLM(db))
    monkeypatch.setattr(fb, "_model_report", lambda *a, **k: (_ for _ in ()).throw(ValueError(SECRET)))
    response = request(api, auth(world.user), sid)
    assert response.status_code == 500 and no_store(response) and SECRET not in response.text and "retry-after" not in response.headers
    assert not db.in_transaction()
    unchanged(db, sid, attempts=1)  # no report, no partial one, and the lease is free
    assert feedback_used(db, world, clock) == 1


# ── The transaction boundary: executable proof ──


def test_the_model_is_called_with_no_transaction_open_after_the_lease_the_attempt_and_the_reservation_were_committed_together(api, db, world, clock, sid, monkeypatch):
    headers = auth(world.user)
    with Timeline(db) as timeline:
        llm = SpyLLM(db, on_call=lambda _llm: timeline.mark("model", session_open=db.in_transaction()))
        install(monkeypatch, llm)
        body = reply_of(request(api, headers, sid))
    assert body["final"] and len(llm.calls) == 1 and llm.in_transaction == [False]
    before, model, after = timeline.split("model")
    assert model[1]["session_open"] is False and model[2] is False  # the session and the engine agree: no transaction was open during the call
    claim = [i for i, e in enumerate(before) if e[0] == "sql" and e[1].startswith("UPDATE interview_sessions SET feedback_attempts")]
    reservation = [i for i, e in enumerate(before) if e[0] == "sql" and "interview_quota" in e[1]]
    commits = [i for i, e in enumerate(before) if e[0] == "commit"]
    assert len(claim) == 1 and reservation and commits
    assert not [i for i in commits if claim[0] < i < max(reservation)]  # T1: the lease, the attempt and the reservation are one transaction ...
    assert max(reservation) < commits[-1]  # ... committed before the model is called
    assert not [e for e in before[commits[-1] + 1:] if e[0] == "sql"]  # and nothing is read or written between that commit and the call
    stores = [e[1] for e in after if e[0] == "sql" and e[1].startswith("UPDATE interview_sessions SET feedback=")]
    assert len(stores) == 1 and fenced_by_lease_token(stores[0])  # T3: after the call, fenced by the lease token
    assert after[-1][0] == "commit" and timeline.open is False and not db.in_transaction()  # nothing is left open


def test_a_failed_model_call_also_happens_outside_any_transaction_and_ends_with_a_fenced_release(api, db, world, clock, sid, monkeypatch):
    headers = auth(world.user)
    with Timeline(db) as timeline:
        llm = SpyLLM(db, fail=True, on_call=lambda _llm: timeline.mark("model", session_open=db.in_transaction()))
        install(monkeypatch, llm)
        body = reply_of(request(api, headers, sid))
    assert (body["final"], body["reason"]) == (False, fb.REASON_MODEL_FAILED)
    before, model, after = timeline.split("model")
    assert model[1]["session_open"] is False and model[2] is False
    releases = [e[1] for e in after if e[0] == "sql" and e[1].startswith("UPDATE interview_sessions SET feedback_lease_until")]
    assert len(releases) == 1 and fenced_by_lease_token(releases[0]) and "interview_sessions.feedback IS NULL" in releases[0]  # fenced, and never over a report
    assert not [e for e in after if e[0] == "sql" and e[1].startswith("UPDATE interview_sessions SET feedback=")]  # nothing was stored
    assert after[-1][0] == "commit" and timeline.open is False and not db.in_transaction()


def test_a_stale_worker_leaves_no_transaction_open_and_its_store_is_fenced_and_changes_nothing(api, db, world, clock, sid, monkeypatch):
    headers, uid = auth(world.user), world.user.id
    with Timeline(db) as timeline:
        def worker_b_takes_over(llm):
            timeline.mark("model", session_open=db.in_transaction())
            clock.advance(LEASE + 1)
            second = other_session(db)
            try:
                fb._claim(second, sid, uid, clock())
            finally:
                second.close()

        install(monkeypatch, SpyLLM(db, on_call=worker_b_takes_over))
        body = reply_of(request(api, headers, sid))
    assert body["reason"] == fb.REASON_LEASE_LOST
    before, model, after = timeline.split("model")
    assert model[1]["session_open"] is False
    assert not db.in_transaction() and timeline.open is False  # the stale worker did not leave a lock or a transaction behind
    assert row(db, sid).feedback is None  # and what its fenced store tried changed no row
