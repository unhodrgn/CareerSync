"""A model-written feedback with U+0000 never reaches the database (M4 S3c.1, D65).

PostgreSQL TEXT and JSONB cannot hold the character, SQLite can, so a report with one passes every SQLite test and fails in production,
after the model has been paid, with a database error. The screens of `make_feedback` do not look for it, so the service does, once, on the
whole report that the model made (every string of `report.to_data()`, the method included) before anything is stored. A report that has
one is dropped whole, never cleaned and never stored in part, and the request goes on as a failed model call: the rules report, provisional
on attempts 1 and 2 and stored as final on the last one. A NUL in a place that the checks of `make_feedback` already drop (a quote that is
not in the transcript, a topic id that is not in the plan) costs only that item. SQLite-runnable; the PostgreSQL side is one test in
test_interview_nul_postgres.py, written and not run."""
import json

import pytest

from app.models import InterviewSession
from app.services import interview_feedback_service as fb
from app.services.interview_plan_service import has_nul

from .interview_feedback_fixtures import SpyLLM, askable_session, feedback_used, install, row
from .interview_fixtures import Clock, build_world

NUL = "\x00"
QUOTE = "Java 트랜잭션 처리를 직접 설계했습니다"  # the candidate line of `askable_session`, which topic c1 shows


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return askable_session(db, world, clock)


def reply(**sections):
    return {"strengths": [], "gaps": [], "improvements": [], "practice_questions": [], **sections}


STRENGTH = {"topic_id": "c1", "text": "구체적인 사례를 들어 설명했습니다.", "quotes": [QUOTE]}
GAP = {"topic_id": "c2", "text": "'Spring Boot' 항목은 이번 연습에서 다루지 못했습니다."}
IMPROVEMENT = "답변은 상황과 역할, 해결 과정과 결과의 순서로 구성해 보세요."
PRACTICE = {"topic_id": "c2", "question": "Spring Boot의 트랜잭션 처리 방식을 설명해 보세요."}
FULL = reply(strengths=[STRENGTH], gaps=[GAP], improvements=[IMPROVEMENT], practice_questions=[PRACTICE])


def with_nul(text):
    """The same sentence with the character in the middle of a word."""
    return text[: len(text) // 2] + NUL + text[len(text) // 2 :]


@pytest.fixture
def stores(monkeypatch):
    """Every report that reaches the persistence operation, as the data that would be written."""
    seen = []
    real = fb._store

    def spy(db, session_id, seeker_id, report, now, *, token):
        seen.append(report.to_data())
        return real(db, session_id, seeker_id, report, now, token=token)

    monkeypatch.setattr(fb, "_store", spy)
    return seen


def nothing_with_nul(*values):
    for value in values:
        assert not has_nul(value) and NUL not in json.dumps(value, ensure_ascii=False)


# ── Normal feedback is unaffected ──


def test_a_full_valid_reply_is_stored_whole_and_nothing_is_dropped(db, world, clock, sid, monkeypatch, stores):
    install(monkeypatch, SpyLLM(db, reply=FULL))
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.reason) == (True, "llm:spy-llm", None)
    assert [s["text"] for s in result.data["strengths"]] == [STRENGTH["text"]] and result.data["strengths"][0]["quotes"] == [QUOTE]
    assert [g["text"] for g in result.data["gaps"]] == [GAP["text"]]
    assert result.data["improvements"] == [IMPROVEMENT]
    assert [q["question"] for q in result.data["practice_questions"]] == [PRACTICE["question"]]
    assert stores == [result.data] and row(db, sid).feedback == result.data
    nothing_with_nul(result.data)


# ── A NUL in each field the model writes ──

MODEL_FIELDS = {
    "a strength sentence": reply(strengths=[{**STRENGTH, "text": with_nul(STRENGTH["text"])}], improvements=[IMPROVEMENT]),
    "a gap sentence": reply(gaps=[{**GAP, "text": with_nul(GAP["text"])}], improvements=[IMPROVEMENT]),
    "an improvement": reply(improvements=[with_nul(IMPROVEMENT)]),
    "a practice question": reply(practice_questions=[{**PRACTICE, "question": with_nul(PRACTICE["question"])}], improvements=[IMPROVEMENT]),
    "one bad improvement among good sections": {**FULL, "improvements": [IMPROVEMENT, with_nul("실제 사례를 들어 답변을 구성해 보세요.")]},
}


@pytest.mark.parametrize("name", list(MODEL_FIELDS), ids=list(MODEL_FIELDS))
def test_a_nul_in_any_sentence_the_model_wrote_drops_the_whole_report_and_nothing_reaches_the_database(db, world, clock, sid, monkeypatch, stores, name):
    llm = SpyLLM(db, reply=MODEL_FIELDS[name])
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    # A failed model call: the rules report, provisional; the attempt and the reservation are spent, the lease is free again
    assert (result.final, result.limited, result.reason, result.method, result.attempts_used) == (False, False, fb.REASON_MODEL_FAILED, "rules", 1)
    assert stores == []  # the persistence operation was never reached
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_lease_token, r.feedback_lease_until, r.feedback_attempts) == (None, None, None, None, 1)
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1
    nothing_with_nul(result.data)
    assert result.data["strengths"] == [] or all(s["text"] != STRENGTH["text"] for s in result.data["strengths"])  # nothing of the model's is kept in part


def test_a_nul_in_the_name_of_the_model_is_refused_too(db, world, clock, sid, monkeypatch, stores):
    install(monkeypatch, SpyLLM(db, model=f"claude{NUL}x"))  # the method is stored as `llm:<model>`
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.reason, result.method) == (False, fb.REASON_MODEL_FAILED, "rules")
    assert stores == [] and row(db, sid).feedback is None
    nothing_with_nul(result.data, result.method)


def test_the_rules_report_after_a_nul_is_the_one_a_failed_model_call_gives(db, world, clock, sid, monkeypatch):
    twin = askable_session(db, world, clock)
    install(monkeypatch, SpyLLM(db, reply=MODEL_FIELDS["an improvement"]))
    refused = fb.ensure(db, world.user, sid, clock=clock)
    install(monkeypatch, SpyLLM(db, fail=True))
    failed = fb.ensure(db, world.user, twin, clock=clock)
    assert refused.data == failed.data and (refused.reason, failed.reason) == (fb.REASON_MODEL_FAILED, fb.REASON_MODEL_FAILED)


def test_on_the_last_attempt_the_rules_report_is_stored_as_final_and_has_no_nul(db, world, clock, sid, monkeypatch, stores):
    db.execute(InterviewSession.__table__.update().where(InterviewSession.id == sid).values(feedback_attempts=fb.settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS - 1))
    db.commit()
    install(monkeypatch, SpyLLM(db, reply=MODEL_FIELDS["an improvement"]))
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.attempts_used, result.reason) == (True, "rules", fb.settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS, None)
    assert len(stores) == 1 and stores[0]["method"] == "rules"  # the persistence operation got the rules report, and only that
    nothing_with_nul(stores[0], row(db, sid).feedback)
    assert row(db, sid).feedback == result.data and row(db, sid).feedback_lease_token is None


# ── A NUL that the checks of `make_feedback` already drop costs only that item ──

DROPPED_BY_THE_CHECKS = {
    "a quote": reply(strengths=[{**STRENGTH, "quotes": [QUOTE + NUL]}], improvements=[IMPROVEMENT]),
    "a topic id of a strength": reply(strengths=[{**STRENGTH, "topic_id": "c1" + NUL}], improvements=[IMPROVEMENT]),
    "a topic id of a gap": reply(gaps=[{**GAP, "topic_id": "c2" + NUL}], improvements=[IMPROVEMENT]),
    "a topic id of a practice question": reply(practice_questions=[{**PRACTICE, "topic_id": "c2" + NUL}], improvements=[IMPROVEMENT]),
}


@pytest.mark.parametrize("name", list(DROPPED_BY_THE_CHECKS), ids=list(DROPPED_BY_THE_CHECKS))
def test_a_nul_in_a_quote_or_a_topic_id_is_dropped_by_the_checks_and_the_rest_is_stored(db, world, clock, sid, monkeypatch, stores, name):
    install(monkeypatch, SpyLLM(db, reply=DROPPED_BY_THE_CHECKS[name]))
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method) == (True, "llm:spy-llm") and result.data["improvements"] == [IMPROVEMENT]
    assert len(stores) == 1
    nothing_with_nul(stores[0], row(db, sid).feedback)
