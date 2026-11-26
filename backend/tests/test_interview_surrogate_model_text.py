"""A lone surrogate in model-written text never reaches the database (M4 S3c, D73; extends D65 (6) and D66 (1)).

PostgreSQL JSONB refuses the escape of a lone surrogate (the diagnostics of test_interview_jsonb_postgres.py), SQLite stores it, so a feedback
report or a plan with one passes every SQLite test and fails in production with a raw database error, after the model has been paid. A
surrogate is handled exactly as U+0000 is, at the same places (test_interview_feedback_nul.py, test_interview_nul.py): a feedback report that
has one is dropped whole and the request goes on as a failed model call (the rules report, provisional, or final on the last attempt); a plan is
refused with `PlanRefused` (the questions the model made, the canonical plan that would be stored), which the lifecycle turns into 422
`INTERVIEW_NOT_AVAILABLE`. Every surrogate is built with `chr`, never written as an escape, which a tool can rewrite into the character.
Nothing here is PostgreSQL-only: with `TEST_DATABASE_URL` set the same tests run on it."""
import dataclasses

import pytest

from ai.career.interview import Question
from ai.interview import InterviewPlan, PlanCriterion, RubricPoint, clean_cv
from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn
from app.services import ai_runtime
from app.services import interview_feedback_service as fb
from app.services import interview_plan_service as plan_service
from app.services import interview_service as svc
from app.services.career_service import interview_blocklists

from .interview_feedback_fixtures import SpyLLM, askable_session, feedback_used, install, row
from .interview_fixtures import SAMPLE_CV, Clock, build_world
from .test_interview_feedback_nul import FULL, GAP, IMPROVEMENT, PRACTICE, QUOTE, STRENGTH, reply, stores  # noqa: F401  (`stores` is a fixture)
from .test_interview_nul import sealed_item

SURROGATES = {
    "a lone high surrogate": chr(0xD800),
    "a lone low surrogate": chr(0xDC00),
    "a high and a low code point side by side": chr(0xD83D) + chr(0xDE00),  # two code points: not the emoji, and not combined
}
KINDS = list(SURROGATES)
ASTRAL = chr(0x1F600)  # one code point, valid text


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return askable_session(db, world, clock)


def inside(text, value):
    """The same sentence with the character in the middle of a word."""
    return text[: len(text) // 2] + value + text[len(text) // 2 :]


def nothing_unstorable(*values):
    for value in values:
        assert not plan_service.has_surrogate(value) and not plan_service.has_nul(value)


# ── The check itself ──


def test_has_surrogate_looks_at_every_string_a_plan_or_a_report_can_hold():
    has = plan_service.has_surrogate
    high, low = SURROGATES["a lone high surrogate"], SURROGATES["a lone low surrogate"]
    for value in SURROGATES.values():
        assert has(value) and has(f"a{value}b")
    assert not has("") and not has("a b") and not has("Java를 썼습니다") and not has(ASTRAL) and not has(f"a{ASTRAL}b")  # valid text, emoji included
    assert has({"k": ["x", ("y", f"z{high}")]}) and has({f"k{low}": 1}) and has({"a": {"b": {"c": [high]}}})
    assert has({"a", f"b{high}"}) and has(frozenset({low}))
    assert not has({"items": [{"n": 1, "ok": True, "none": None, "f": 1.5, "s": "text"}]}) and not has(None) and not has(3)
    question = Question("질문", 1, "Java", "technical", "확인", ("팁",), None)
    assert not has(question) and not has([question])
    for field in ("question", "criterion_name", "kind", "intent", "cv_quote"):
        assert has(dataclasses.replace(question, **{field: f"x{high}"})), field
    assert has(dataclasses.replace(question, answer_tips=("팁", f"x{low}")))
    assert not has(Question)  # a class is not an instance
    assert not has("a\x00b") and not plan_service.has_nul(f"a{high}b")  # each one looks for its own character only


# ── A feedback report: a surrogate in each field the model writes ──

FIELD_NAMES = ["a strength sentence", "a gap sentence", "an improvement", "a practice question", "one bad improvement among good sections"]


def model_fields(value):
    return {
        "a strength sentence": reply(strengths=[{**STRENGTH, "text": inside(STRENGTH["text"], value)}], improvements=[IMPROVEMENT]),
        "a gap sentence": reply(gaps=[{**GAP, "text": inside(GAP["text"], value)}], improvements=[IMPROVEMENT]),
        "an improvement": reply(improvements=[inside(IMPROVEMENT, value)]),
        "a practice question": reply(practice_questions=[{**PRACTICE, "question": inside(PRACTICE["question"], value)}], improvements=[IMPROVEMENT]),
        "one bad improvement among good sections": {**FULL, "improvements": [IMPROVEMENT, inside("실제 사례를 들어 답변을 구성해 보세요.", value)]},
    }


@pytest.mark.parametrize("kind", KINDS, ids=KINDS)
@pytest.mark.parametrize("name", FIELD_NAMES, ids=FIELD_NAMES)
def test_a_surrogate_in_any_sentence_the_model_wrote_drops_the_whole_report_and_nothing_reaches_the_database(db, world, clock, sid, monkeypatch, stores, name, kind):
    llm = SpyLLM(db, reply=model_fields(SURROGATES[kind])[name])
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    # A failed model call: the rules report, provisional; the attempt and the reservation are spent, the lease is free again
    assert (result.final, result.limited, result.reason, result.method, result.attempts_used) == (False, False, fb.REASON_MODEL_FAILED, "rules", 1)
    assert stores == []  # the persistence operation was never reached
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_lease_token, r.feedback_lease_until, r.feedback_attempts) == (None, None, None, None, 1)
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1
    nothing_unstorable(result.data)
    assert result.data["strengths"] == [] or all(s["text"] != STRENGTH["text"] for s in result.data["strengths"])  # nothing of the model's is kept in part


@pytest.mark.parametrize("kind", KINDS, ids=KINDS)
def test_a_surrogate_in_the_name_of_the_model_is_refused_too(db, world, clock, sid, monkeypatch, stores, kind):
    install(monkeypatch, SpyLLM(db, model=f"claude{SURROGATES[kind]}x"))  # the method is stored as `llm:<model>`
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.reason, result.method) == (False, fb.REASON_MODEL_FAILED, "rules")
    assert stores == [] and row(db, sid).feedback is None
    nothing_unstorable(result.data, result.method)


def test_the_rules_report_after_a_surrogate_is_the_one_a_failed_model_call_gives(db, world, clock, sid, monkeypatch):
    twin = askable_session(db, world, clock)
    install(monkeypatch, SpyLLM(db, reply=model_fields(SURROGATES["a lone high surrogate"])["an improvement"]))
    refused = fb.ensure(db, world.user, sid, clock=clock)
    install(monkeypatch, SpyLLM(db, fail=True))
    failed = fb.ensure(db, world.user, twin, clock=clock)
    assert refused.data == failed.data and (refused.reason, failed.reason) == (fb.REASON_MODEL_FAILED, fb.REASON_MODEL_FAILED)


def test_on_the_last_attempt_the_rules_report_is_stored_as_final_and_has_no_surrogate(db, world, clock, sid, monkeypatch, stores):
    db.execute(InterviewSession.__table__.update().where(InterviewSession.id == sid).values(feedback_attempts=fb.settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS - 1))
    db.commit()
    install(monkeypatch, SpyLLM(db, reply=model_fields(SURROGATES["a lone low surrogate"])["an improvement"]))
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.attempts_used, result.reason) == (True, "rules", fb.settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS, None)
    assert len(stores) == 1 and stores[0]["method"] == "rules"  # the persistence operation got the rules report, and only that
    nothing_unstorable(stores[0], row(db, sid).feedback)
    assert row(db, sid).feedback == result.data and row(db, sid).feedback_lease_token is None


# ── What is not changed ──


def test_a_valid_emoji_is_not_a_surrogate_and_the_report_is_stored_whole(db, world, clock, sid, monkeypatch, stores):
    text = IMPROVEMENT + " " + ASTRAL
    install(monkeypatch, SpyLLM(db, reply=reply(improvements=[text])))
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.reason) == (True, "llm:spy-llm", None) and result.data["improvements"] == [text]
    assert len(stores) == 1 and row(db, sid).feedback["improvements"] == [text]


DROPPED_BY_THE_CHECKS = {
    "a quote": lambda v: reply(strengths=[{**STRENGTH, "quotes": [QUOTE + v]}], improvements=[IMPROVEMENT]),
    "a topic id of a strength": lambda v: reply(strengths=[{**STRENGTH, "topic_id": "c1" + v}], improvements=[IMPROVEMENT]),
    "a topic id of a gap": lambda v: reply(gaps=[{**GAP, "topic_id": "c2" + v}], improvements=[IMPROVEMENT]),
    "a topic id of a practice question": lambda v: reply(practice_questions=[{**PRACTICE, "topic_id": "c2" + v}], improvements=[IMPROVEMENT]),
}


@pytest.mark.parametrize("name", list(DROPPED_BY_THE_CHECKS), ids=list(DROPPED_BY_THE_CHECKS))
def test_a_surrogate_in_a_quote_or_a_topic_id_is_dropped_by_the_checks_and_the_rest_is_stored(db, world, clock, sid, monkeypatch, stores, name):
    install(monkeypatch, SpyLLM(db, reply=DROPPED_BY_THE_CHECKS[name](SURROGATES["a lone high surrogate"])))
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method) == (True, "llm:spy-llm") and result.data["improvements"] == [IMPROVEMENT]
    assert len(stores) == 1
    nothing_unstorable(stores[0], row(db, sid).feedback)


# ── A plan ──


@pytest.mark.parametrize("kind", KINDS, ids=KINDS)
def test_a_bank_with_a_surrogate_is_refused_by_the_creation_of_the_session_and_no_plan_is_stored(db, world, clock, monkeypatch, kind):
    """The service level, through `create_session`: the real question bank, with a surrogate added to the tips of every question, as a client that
    hands back an object (and not JSON text, which the Anthropic client's parser refuses) could deliver it. The refusal is the one of a NUL.
    `InterviewLlmOut` takes a surrogate in `answer_tips` when it is built from a dict (and refuses one in `question`), so a plan double that
    validates its own answer cannot carry one in the question text: the bank is changed after it is made."""
    made = []
    real = plan_service.make_bank

    def tainted(*args, **kwargs):
        bank, method = real(*args, **kwargs)
        made.append(len(bank))
        return [dataclasses.replace(q, answer_tips=(*q.answer_tips, "팁" + SURROGATES[kind])) for q in bank], method

    monkeypatch.setattr(plan_service, "make_bank", tainted)
    with pytest.raises(AppError) as error:
        svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-26", clock=clock)
    assert (error.value.status_code, error.value.code) == (422, "INTERVIEW_NOT_AVAILABLE")
    db.rollback()
    session = db.query(InterviewSession).filter_by(seeker_id=world.user.id).one()
    assert len(made) == 1 and made[0] > 0  # a bank was made, and it was refused as a whole
    assert (session.status, session.end_reason, session.plan, session.plan_sha256) == ("aborted", "plan_unavailable", None, None)
    assert db.query(InterviewTurn).count() == 0


def test_a_bank_field_that_would_be_discarded_is_refused_too(monkeypatch):
    """The model's `cv_quote` is cleared before the plan is built, so sealing would never see a surrogate in it; the bank check refuses it
    anyway: the plan is not made from a model answer that has one."""
    from app.services.interview_plan_service import build_canonical_plan, limits_from_settings

    bank = [Question("Java를 실무에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요.", 1, "Java", "technical", "Java 경험 확인", ("구체적으로",), "인용" + SURROGATES["a lone high surrogate"] + "문장")]
    monkeypatch.setattr(plan_service, "make_bank", lambda *args, **kwargs: (bank, "rules"))
    criteria = [PlanCriterion(1, "Java", "skill", "Java 개발 경험", "core", 0)]
    arguments = dict(
        stored_cv=SAMPLE_CV, job_title="Backend Engineer", job_text="Java/Spring 백엔드 API 개발", criteria=criteria, blocklists=interview_blocklists(),
        embedder=ai_runtime.embedder(), skills=ai_runtime.skills(), limits=limits_from_settings(), llm=None,
    )
    with pytest.raises(plan_service.PlanRefused) as refused:
        build_canonical_plan(**arguments)
    assert refused.value.code == "surrogate_bank"
    monkeypatch.setattr(plan_service, "make_bank", lambda *args, **kwargs: ([dataclasses.replace(bank[0], cv_quote=None)], "rules"))
    assert build_canonical_plan(**arguments).sha256  # the same bank without the character is accepted


def plan_fields(value):
    return {
        "question": {"question": f"Java를 실무에서 어떻게{value} 사용했는지 설명해 주세요."},
        "rephrase": {"rephrase": f"조금 더 쉽게{value} 말씀해 주세요."},
        "intent": {"intent": f"Java 경험{value} 확인"},
        "answer_tips": {"answer_tips": (f"구체적으로{value} 설명해 보세요",)},
        "criterion_name": {"criterion_name": f"Java{value} 활용"},
        "rubric_text": {"rubric": (RubricPoint("p1", f"핵심{value} 개념과 동작 방식", ("개념", "동작"), 1), RubricPoint("p2", "실제 사용 사례", ("사용", "적용"), 1))},
    }


@pytest.mark.parametrize("kind", KINDS, ids=KINDS)
@pytest.mark.parametrize("name", list(plan_fields("")), ids=list(plan_fields("")))
def test_a_canonical_plan_with_a_surrogate_in_any_text_field_is_refused_at_sealing(name, kind):
    plan = InterviewPlan((sealed_item(**plan_fields(SURROGATES[kind])[name]),), ())
    with pytest.raises(plan_service.PlanRefused) as refused:
        plan_service.seal(plan, clean_cv(SAMPLE_CV), interview_blocklists())
    assert refused.value.code == "surrogate_plan", name  # and not an encoding error from the digest


def test_a_plan_with_a_valid_emoji_is_still_sealed():
    plan = InterviewPlan((sealed_item(question=f"Java를 실무에서 어떻게 사용했는지 {ASTRAL} 설명해 주세요."),), ())
    sealed = plan_service.seal(plan, clean_cv(SAMPLE_CV), interview_blocklists())
    assert sealed.sha256 and not plan_service.has_surrogate(sealed.data)
