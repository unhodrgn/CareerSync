"""Plan validation (ai/interview/validate.py; docs/DECISIONS.md D61): the one path every plan takes, whoever made it.

Synthetic canary data only. A canary is text that uses no word of the age, gender and military-service vocabulary, so only
the removed-line check or the structure can refuse it; the sensitive strings are the vocabulary's. Plans are handcrafted,
built by `build_plan` from a hostile question bank, and deserialized from JSON with forged fields; all of them are run
through `validate_plan` directly and through `InterviewEngine.__init__`."""
import dataclasses
import json

import pytest

import ai.interview.engine as engine_module
import ai.interview.plan as plan_module
import ai.interview.validate as validate_module
from ai.career.interview import Question
from ai.interview import (
    InterviewEngine,
    InterviewPlan,
    PlanCriterion,
    PlanItem,
    RubricPoint,
    build_plan,
    is_sensitive,
    prepare_turn,
    validate_plan,
)
from ai.interview.types import RUBRIC_NOTICE, UncoveredCriterion
from ai.parsing.pii import mask_pii
from ai.tests.helpers import SKILLS
from ai.tests.interview_helpers import BLOCKLISTS, CRITERIA, GOOD, MASKED_CV, crit, make_engine, make_plan
from ai.interview import rules

CV = """김지원
CANARY-HEADER 지원 직무 백엔드
성별: 여

인적사항
CANARY-PERSONAL 비고 기록 7788

경력
(주)넥스트코드 | 백엔드 개발자 2021.03 ~ 2023.02
- Java, Spring Boot 기반 주문 API 개발
- MySQL 인덱스 튜닝으로 조회 속도 40% 개선

자격증
정보처리기사 2020.08
"""
MASKED = mask_pii(CV, ["김지원"], SKILLS).text
REMOVED_LINE = "CANARY-PERSONAL 비고 기록 7788"
GOOD_LINE = "Java, Spring Boot 기반 주문 API 개발"
CANARIES = ("CANARY-HEADER", "CANARY-PERSONAL")
GOOD_Q = "Java를 실무에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요."


def item(**kw) -> PlanItem:
    base = dict(
        topic_id="c1",
        kind="technical",
        question=GOOD_Q,
        rephrase=rules.GENERIC_REPHRASE,
        rubric=(RubricPoint("p1", "핵심 개념과 동작 방식", ("개념", "동작"), 1), RubricPoint("p2", "실제로 사용한 사례", ("사용", "적용"), 1)),
        topic_keywords=("java",),
        criterion_id=1,
        criterion_name="Java 활용 능력",
        importance="핵심",
        intent="Java 활용 경험 확인",
        answer_tips=("구체적으로",),
        cv_quote=None,
    )
    return PlanItem(**{**base, **kw})


def check(*items: PlanItem, cv_text: str | None = MASKED, uncovered=()):
    return validate_plan(InterviewPlan(tuple(items), tuple(uncovered)), blocklists=BLOCKLISTS, cv_text=cv_text, skills=SKILLS)


def dump(plan: InterviewPlan) -> str:
    return json.dumps(plan.to_dict(), ensure_ascii=False)


# ── The baseline ──


def test_a_plan_the_builder_made_is_unchanged_and_validation_is_idempotent():
    plan = make_plan()
    first = validate_plan(plan, blocklists=BLOCKLISTS, cv_text=MASKED_CV)
    assert first.plan == plan and first.issues == ()
    assert validate_plan(first.plan, blocklists=BLOCKLISTS, cv_text=MASKED_CV) == first


def test_the_engine_keeps_a_cv_quote_only_when_it_has_the_cv():
    plan = make_plan()
    assert plan.items[0].topic_id == "warmup" and plan.items[0].cv_quote
    without = InterviewEngine(plan, blocklists=BLOCKLISTS).state.plan  # the realtime agent has no CV text
    assert without.items[0].cv_quote is None
    assert [dataclasses.replace(i, cv_quote=None) for i in plan.items] == list(without.items)  # nothing else changed
    assert InterviewEngine(plan, blocklists=BLOCKLISTS, cv_text=MASKED_CV).state.plan == plan


# ── Each field of an item ──

SENSITIVE_QUESTIONS = [
    "군 복무는 어디서 하셨나요?", "20대 후반이신가요? Java는 어떻게 쓰셨나요?", "Tell me about your military service.",
    "How old are you?", "성별을 알려 주세요.", REMOVED_LINE + " 에 대해 설명해 주세요.",
    "연락은 hr@example.com 으로 주세요.", "합격 가능성을 알려 드릴게요.", "[이름]님의 경험을 말씀해 주세요.", "x" * 400, "", "   ",
]


@pytest.mark.parametrize("question", SENSITIVE_QUESTIONS)
def test_a_question_that_fails_the_spoken_screens_drops_the_item_and_reports_the_criterion(question):
    report = check(item(question=question))
    assert report.plan.items == ()
    assert [(u.criterion_id, u.reason) for u in report.plan.uncovered] == [(1, "no_question")]
    assert "c1:question" in report.issues


@pytest.mark.parametrize("rephrase", ["군 복무 중 경험도 괜찮아요.", "나이와 상관없이 말씀해 주세요.", REMOVED_LINE + " 를 떠올려 보세요.", "합격하려면 말씀해 주세요.", "y" * 300])
def test_a_bad_rephrase_is_replaced_by_the_generic_one(rephrase):
    report = check(item(rephrase=rephrase))
    assert report.plan.items[0].rephrase == rules.GENERIC_REPHRASE and "c1:rephrase" in report.issues


@pytest.mark.parametrize("intent", ["병역 이행 여부 확인", "Check military service", REMOVED_LINE + " 확인", "z" * 300, 5, None])
def test_a_bad_intent_is_emptied(intent):
    assert check(item(intent=intent)).plan.items[0].intent == ""


def test_bad_tips_are_filtered_one_by_one():
    tips = ("구체적으로", "군필 여부를 먼저 말하기", "Mention your gender first", REMOVED_LINE, "결과로 마무리하기", 7, "a" * 200)
    kept = check(item(answer_tips=tips)).plan.items[0].answer_tips
    assert kept == ("구체적으로", "결과로 마무리하기")


@pytest.mark.parametrize(
    "rubric",
    [
        (RubricPoint("p1", "남성 지원자 우대", ("우대",), 1), RubricPoint("p2", "실제로 사용한 사례", ("사용",), 1)),
        (RubricPoint("p1", REMOVED_LINE, ("기록",), 1), RubricPoint("p2", "실제로 사용한 사례", ("사용",), 1)),
        (RubricPoint("p1", "병역", ("병역",), 1), RubricPoint("p2", "사례", ("사용",), 1)),
        (RubricPoint("x1", "핵심 개념과 동작 방식", ("개념",), 1), RubricPoint("p2", "실제로 사용한 사례", ("사용",), 1)),
        (RubricPoint("p1", "핵심 개념과 동작 방식", ("개념",), 1), RubricPoint("p1", "실제로 사용한 사례", ("사용",), 1)),
        (RubricPoint("p1", "핵심 개념과 동작 방식", ("개념",), 1),),
        tuple(RubricPoint(f"p{i}", f"기대 답변 {i}번 항목", ("항목",), 1) for i in range(1, 7)),
        (RubricPoint("p1", "핵심 개념과 동작 방식", (), 1), RubricPoint("p2", "실제로 사용한 사례", ("사용",), 1)),
        (RubricPoint("p1", "핵심 개념과 동작 방식", ("27살", "군필"), 1), RubricPoint("p2", "실제로 사용한 사례", ("사용",), 1)),
        ("not a rubric point",),
        (),
    ],
)
def test_a_bad_rubric_is_replaced_by_a_clean_generic_one(rubric):
    report = check(item(rubric=rubric))
    points = report.plan.items[0].rubric
    assert "c1:rubric" in report.issues
    assert 2 <= len(points) <= 4 and [p.id for p in points] == [f"p{i}" for i in range(1, len(points) + 1)]
    assert all(p.source == "ai_generated" and p.keywords and 1 <= p.min_hits <= len(p.keywords) for p in points)
    assert not is_sensitive(dump(report.plan)) and not any(c in dump(report.plan) for c in CANARIES)


def test_a_good_rubric_survives_and_min_hits_is_clamped():
    odd = (RubricPoint("p1", "핵심 개념과 동작 방식", ("개념", "동작"), 99), RubricPoint("p2", "실제로 사용한 사례", ("사용",), True))  # type: ignore[arg-type]
    points = check(item(rubric=odd)).plan.items[0].rubric
    assert [(p.id, p.text) for p in points] == [("p1", "핵심 개념과 동작 방식"), ("p2", "실제로 사용한 사례")]
    assert [p.min_hits for p in points] == [2, 1]


def test_keywords_are_filtered_and_never_sensitive():
    kept = check(item(topic_keywords=("java", "27살", "군필", REMOVED_LINE, "x", "spring boot", 5, "a" * 40, "java"))).plan.items[0].topic_keywords  # type: ignore[arg-type]
    assert kept == ("java",)


def test_a_criterion_name_about_the_topics_is_dropped_and_the_item_stays():
    report = check(item(criterion_name="남성 우대 Java"))
    assert report.plan.items[0].criterion_name is None and "c1:criterion_name" in report.issues


@pytest.mark.parametrize(
    "bad",
    [
        dict(topic_id="c1;x"), dict(topic_id="c0x1"), dict(topic_id="warmup2"), dict(topic_id=""), dict(topic_id=None),
        dict(criterion_id=2), dict(criterion_id=None), dict(importance="25"), dict(importance="핵심점수"), dict(importance=None),
        dict(kind="weight"), dict(kind=""),
    ],
)
def test_forged_ids_kinds_and_labels_drop_the_item(bad):
    report = check(item(**bad))
    assert report.plan.items == ()


def test_something_that_is_not_an_item_is_dropped():
    report = validate_plan(InterviewPlan(("c1", None, item())), blocklists=BLOCKLISTS)  # type: ignore[arg-type]
    assert [i.topic_id for i in report.plan.items] == ["c1"] and report.issues.count("item:type") == 2


def test_a_second_item_with_the_same_topic_is_dropped():
    report = check(item(), item(question="Java의 장단점을 사례와 함께 설명해 주세요."))
    assert len(report.plan.items) == 1 and "c1:duplicate" in report.issues


def test_a_general_item_carries_no_criterion_fields():
    warm = item(topic_id="warmup", kind="experience", criterion_id=None, criterion_name="Java", importance="핵심")
    out = check(warm).plan.items[0]
    assert (out.criterion_id, out.criterion_name, out.importance) == (None, None, None)


# ── cv_quote ──


@pytest.mark.parametrize(
    ("quote", "cv_text", "kept"),
    [
        (GOOD_LINE, MASKED, True),
        (GOOD_LINE, None, False),  # no CV, nothing shows where it came from
        (REMOVED_LINE, MASKED, False),  # a removed line is not in the cleaned CV
        ("저는 스물일곱 살입니다 그리고 개발자입니다", MASKED, False),
        ("지어낸 문장입니다 가나다라마바사 아자차카", MASKED, False),
        ("가" * 400, MASKED, False),
        (None, MASKED, None),
    ],
)
def test_a_cv_quote_survives_only_when_it_is_in_the_cleaned_cv(quote, cv_text, kept):
    out = check(item(topic_id="warmup", kind="experience", criterion_id=None, criterion_name=None, importance=None, cv_quote=quote), cv_text=cv_text)
    got = out.plan.items[0].cv_quote
    assert got == (GOOD_LINE if kept else None)


# ── The rest of the plan ──


def test_uncovered_entries_bank_method_and_notice_are_validated():
    entries = [
        UncoveredCriterion(2, "남성 우대", "중요", "no_slot"),
        UncoveredCriterion(3, "협업 태도", "일반", "weird"),
        UncoveredCriterion(4, "가중치", "25", "no_slot"),  # type: ignore[arg-type]
        UncoveredCriterion("5", "x", "핵심", "no_slot"),  # type: ignore[arg-type]
    ]
    plan = InterviewPlan((item(),), tuple(entries), rubric_notice="이 면접은 합격을 보장합니다", bank_method="evil\nmethod")
    out = validate_plan(plan, blocklists=BLOCKLISTS).plan
    assert [(u.criterion_id, u.name, u.importance, u.reason) for u in out.uncovered] == [(2, "(제외됨)", "중요", "no_slot"), (3, "협업 태도", "일반", "no_question")]
    assert out.rubric_notice == RUBRIC_NOTICE and out.bank_method == "rules"
    assert validate_plan(dataclasses.replace(plan, bank_method="llm:claude-sonnet-5-5"), blocklists=BLOCKLISTS).plan.bank_method == "llm:claude-sonnet-5-5"


def test_a_malformed_plan_never_raises_and_a_non_plan_is_refused():
    broken = PlanItem(
        topic_id="c1", kind="technical", question=GOOD_Q, rephrase=None, rubric=("x", 5), topic_keywords=123,  # type: ignore[arg-type]
        criterion_id=1, criterion_name=7, importance="핵심", intent=object(), answer_tips="not a tuple", cv_quote=9,  # type: ignore[arg-type]
    )
    out = check(broken).plan.items[0]
    assert out.rephrase == rules.GENERIC_REPHRASE and out.intent == "" and out.answer_tips == () and out.topic_keywords == ()
    assert out.criterion_name is None and out.cv_quote is None and 2 <= len(out.rubric) <= 4
    with pytest.raises(TypeError):
        validate_plan("not a plan")  # type: ignore[arg-type]


# ── The engine and the builder use the same path ──


def test_the_builder_and_the_engine_call_the_same_validator(monkeypatch):
    assert plan_module.validate_plan is validate_module.validate_plan is engine_module.validate_plan
    calls = []
    real = validate_module.validate_plan

    def spy(plan, **kw):
        calls.append(kw.get("cv_text"))
        return real(plan, **kw)

    monkeypatch.setattr(plan_module, "validate_plan", spy)
    monkeypatch.setattr(engine_module, "validate_plan", spy)
    plan = make_plan()
    InterviewEngine(plan, blocklists=BLOCKLISTS, cv_text=MASKED_CV)
    assert calls == [MASKED_CV, MASKED_CV]  # once at the end of build_plan, once in the engine's constructor


def test_the_engine_validates_a_handcrafted_plan_before_anything_is_spoken():
    bad_question = item(topic_id="c1", question="군 복무는 어디서 하셨나요?")
    bad_rubric = item(
        topic_id="c2", criterion_id=2, question="REST API를 설계하고 문서화한 경험을 설명해 주세요.", criterion_name="프로젝트 경험",
        rubric=(RubricPoint("p1", "남성 지원자 우대", ("우대",), 1), RubricPoint("p2", "설계한 API", ("설계",), 1)),
    )
    engine = InterviewEngine(InterviewPlan((bad_question, bad_rubric)), blocklists=BLOCKLISTS)
    assert [i.topic_id for i in engine.state.plan.items] == ["c2"]
    assert "c1:question" in engine.plan_issues and "c2:rubric" in engine.plan_issues
    assert [(u.criterion_id, u.reason) for u in engine.state.plan.uncovered] == [(1, "no_question")]
    first = engine.start()
    assert not is_sensitive(first.text)
    request = prepare_turn(engine, "REST API를 설계하고 Swagger로 문서화했습니다. 프로젝트에서 설계와 개발을 진행했습니다.")
    assert request is not None and "남성" not in request.user
    context = engine.turn_context("REST API를 설계했습니다")
    assert not any(is_sensitive(text) for _, text in context.rubric)


def test_a_deserialized_plan_with_forged_fields_takes_the_same_path():
    plan = build_plan(CRITERIA, (), MASKED, [GOOD_LINE], BLOCKLISTS, skills=SKILLS)
    data = json.loads(json.dumps(plan.to_dict()))
    data["items"][1]["question"] = "군 복무는 어디서 하셨나요?"
    data["items"][2]["intent"] = "병역 이행 여부 확인"
    data["items"][2]["rubric"][0]["text"] = "남성 지원자 우대"
    data["items"][3]["answer_tips"] = [REMOVED_LINE, "구체적으로"]
    data["items"][0]["cv_quote"] = REMOVED_LINE
    data["items"][0]["weight"] = 25  # an unknown field is ignored, never carried
    data["rubric_notice"] = "합격을 보장합니다"
    revived = InterviewPlan.from_dict(json.loads(json.dumps(data)))
    engine = InterviewEngine(revived, blocklists=BLOCKLISTS, cv_text=MASKED)
    text = dump(engine.state.plan)
    assert not is_sensitive(text) and not any(c in text for c in CANARIES) and "weight" not in text and "합격" not in text
    assert set(engine.plan_issues) == {"warmup:cv_quote", "c1:question", "c2:intent_or_tips", "c2:rubric", "c4:intent_or_tips"}
    assert engine.state.plan.items[0].cv_quote is None


# ── build_plan does not trust a question bank ──

HOSTILE = [
    ("question", "군 복무는 어디서 하셨나요?"),
    ("question", REMOVED_LINE + " 에 대해 설명해 주세요."),
    ("question", "합격 여부를 알려 드릴게요."),
    ("question", "자세한 내용은 https://example.com/x 를 보세요."),
    ("intent", "병역 이행 여부 확인"),
    ("intent", REMOVED_LINE),
    ("tips", ("군필 여부를 먼저 말하기",)),
    ("tips", (REMOVED_LINE,)),
    ("cv_quote", REMOVED_LINE),
    ("cv_quote", "병역: 군필 육군 병장 만기전역"),
]


@pytest.mark.parametrize(("field", "value"), HOSTILE)
@pytest.mark.parametrize("slot", ["criterion", "general_experience", "general_behavioral"])
def test_build_plan_does_not_trust_any_field_of_a_question_bank(slot, field, value):
    base = dict(question="프로젝트에서 맡은 역할과 기여를 구체적으로 설명해 주세요.", intent="역할 확인", tips=("구체적으로",), cv_quote=None)
    base[field] = value
    kind = "behavioral" if slot == "general_behavioral" else "experience"
    cid = 1 if slot == "criterion" else None
    bank = [Question(base["question"], cid, "Java 활용 능력" if cid else None, kind, base["intent"], base["tips"], base["cv_quote"])]
    plan = build_plan(CRITERIA, bank, MASKED, [GOOD_LINE], BLOCKLISTS, skills=SKILLS)
    text = dump(plan)
    assert not is_sensitive(text) and not any(c in text for c in CANARIES)
    assert plan.items  # the plan is still made; the hostile question is replaced by a template


def test_a_criterion_question_that_quotes_a_removed_line_is_replaced_by_the_template():
    bank = [Question(GOOD_Q, 1, "Java 활용 능력", "technical", "확인", ("구체적으로",), REMOVED_LINE)]
    plan = build_plan(CRITERIA, bank, MASKED, [], BLOCKLISTS, skills=SKILLS)
    c1 = next(i for i in plan.items if i.topic_id == "c1")
    assert c1.question != GOOD_Q and c1.cv_quote is None and REMOVED_LINE not in dump(plan)


def test_a_criterion_question_with_an_invented_quote_keeps_the_question_and_loses_the_quote():
    bank = [Question(GOOD_Q, 1, "Java 활용 능력", "technical", "확인", ("구체적으로",), "지어낸 문장입니다 가나다라마바사 아자차카")]
    plan = build_plan(CRITERIA, bank, MASKED, [], BLOCKLISTS, skills=SKILLS)
    c1 = next(i for i in plan.items if i.topic_id == "c1")
    assert c1.question == GOOD_Q and c1.cv_quote is None


def test_a_criterion_question_may_keep_a_real_quote():
    bank = [Question(GOOD_Q, 1, "Java 활용 능력", "technical", "확인", ("구체적으로",), GOOD_LINE)]
    plan = build_plan(CRITERIA, bank, MASKED, [], BLOCKLISTS, skills=SKILLS)
    assert next(i for i in plan.items if i.topic_id == "c1").cv_quote == GOOD_LINE


def test_a_description_with_sentences_about_the_topics_gives_a_clean_rubric():
    criteria = [crit(1, "Java 활용 능력", "skill", "Java 17 사용 경험. 병역필 우대. 남성 선호. Spring Boot API 개발 경험", "핵심")]
    plan = build_plan(criteria, (), MASKED, [], BLOCKLISTS, skills=SKILLS)
    texts = [p.text for i in plan.items for p in i.rubric]
    assert any("Java 17 사용 경험" in t for t in texts) and not is_sensitive(" ".join(texts))


def test_a_criterion_name_about_the_topics_is_reported_not_planned():
    plan = build_plan([crit(1, "남성 우대", "other", "", "핵심"), crit(2, "Java 활용 능력", "skill", "Java 17 사용 경험", "핵심")], (), MASKED, [], BLOCKLISTS, skills=SKILLS)
    assert [i.topic_id for i in plan.items if i.criterion_id is not None] == ["c2"]
    assert [(u.criterion_id, u.name, u.reason) for u in plan.uncovered] == [(1, "(제외됨)", "no_question")]


def test_lines_a_caller_passes_get_the_evidence_filters_too():
    """A heading, a short fragment and a line with a placeholder ground no warm-up, however the caller found them."""
    plan = build_plan(CRITERIA, (), MASKED, ["경력", "Java", "[이메일] 으로 연락", REMOVED_LINE, GOOD_LINE], BLOCKLISTS, skills=SKILLS)
    assert plan.items[0].topic_id == "warmup" and plan.items[0].cv_quote == GOOD_LINE
    assert GOOD["warmup"]  # the shared helper answers still fit the generic warm-up rubric
