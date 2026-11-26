"""The interview plan (ai/interview/plan.py, D51, D57): deterministic, 핵심 first and always covered, a CV-grounded warm-up,
one behavioral question, 2-4 rubric points per item, no weights, no duplicates, the D21 bank and blocklists reused."""
import dataclasses
import json

import pytest

from ai.career.interview import CriterionInfo, interview_rules
from ai.guardrails.evidence import verify_quotes
from ai.interview import InterviewLimits, InterviewPlan, PlanCriterion, PlanItem, build_plan, evidence_lines
from ai.interview.types import AI_GENERATED, IMPORTANCE_RANK, RUBRIC_NOTICE, RubricPoint
from ai.tests.interview_helpers import BLOCKLISTS, CRITERIA, CV_LINES, MASKED_CV, crit, make_plan, q


def ids(plan: InterviewPlan) -> list[str]:
    return [i.topic_id for i in plan.items]


def test_the_plan_is_deterministic_and_independent_of_the_order_criteria_arrive_in():
    first = make_plan().to_dict()
    assert make_plan().to_dict() == first
    assert make_plan(criteria=list(reversed(CRITERIA))).to_dict() == first


def test_the_default_plan_shape():
    plan = make_plan()
    assert ids(plan) == ["warmup", "c1", "c2", "c4", "behavioral"]  # warm-up, 핵심, 핵심, 중요, behavioral
    assert [u.criterion_id for u in plan.uncovered] == [3] and plan.uncovered[0].reason == "no_slot"  # the 일반 one found no slot


def test_every_core_criterion_is_covered_and_importance_orders_the_rest():
    criteria = [
        crit(1, "Java 활용", "skill", "Java 17", "일반", 0),
        crit(2, "프로젝트 경험", "project", "API 설계", "핵심", 3),
        crit(3, "SQL 활용", "skill", "SQL 튜닝", "중요", 1),
        crit(4, "Spring 활용", "skill", "Spring Boot", "핵심", 2),
        crit(5, "협업 태도", "other", "코드 리뷰", "핵심", 4),
    ]
    plan = make_plan(criteria)
    topics = ids(plan)
    assert {"c2", "c4", "c5"} <= set(topics)  # all 핵심, whatever their position in the job
    ranks = [IMPORTANCE_RANK[i.importance] for i in plan.items if i.importance]
    assert ranks == sorted(ranks)  # 핵심 -> 중요 -> 일반
    core_order = [i.criterion_id for i in plan.items if i.importance == "핵심"]
    assert core_order == [4, 2, 5]  # inside one importance level: the job's own order (position)


def test_a_core_criterion_outranks_the_warm_up():
    criteria = [crit(n, f"기술 {n}", "skill", f"기술{n} 사용", "핵심") for n in range(1, 5)] + [crit(5, "전공", "education", "", "중요")]
    plan = make_plan(criteria)
    assert ids(plan) == ["c1", "c2", "c3", "c4", "behavioral"]  # four 핵심 need the slot the warm-up would take
    assert [u.criterion_id for u in plan.uncovered] == [5]


def test_a_criterion_without_a_slot_is_listed_never_dropped_silently():
    plan = make_plan(limits=InterviewLimits(max_questions=3))
    assert len(plan.items) == 3 and plan.items[-1].topic_id == "behavioral"
    covered = {i.criterion_id for i in plan.items if i.criterion_id}
    assert covered | {u.criterion_id for u in plan.uncovered} == {c.id for c in CRITERIA}  # every criterion is somewhere
    assert {u.reason for u in plan.uncovered} == {"no_slot"}


def test_the_number_of_questions_never_exceeds_the_cap():
    many = [crit(n, f"기술 {n}", "skill", f"기술{n} 사용", "핵심" if n < 3 else "일반") for n in range(1, 10)]
    assert len(make_plan(many).items) == 5
    assert len(make_plan(many, limits=InterviewLimits(max_questions=2)).items) == 2


def test_one_behavioral_question_comes_last():
    plan = make_plan()
    behavioral = [i for i in plan.items if i.kind == "behavioral" and i.criterion_id is None]
    assert len(behavioral) == 1 and plan.items[-1] is behavioral[0] and behavioral[0].topic_id == "behavioral"


def test_the_warm_up_quotes_a_verified_line_of_the_candidates_own_cv():
    warmup = make_plan().items[0]
    assert warmup.topic_id == "warmup" and warmup.cv_quote in CV_LINES
    assert verify_quotes([warmup.cv_quote], MASKED_CV) == [warmup.cv_quote]  # verified against the masked CV
    assert warmup.cv_quote in warmup.question
    assert warmup.criterion_id is None and warmup.importance is None


def test_without_cv_evidence_there_is_no_warm_up():
    plan = make_plan(cv_lines=[])
    assert "warmup" not in ids(plan) and ids(plan)[0] == "c1"


def test_a_cv_line_that_is_not_in_the_cv_cannot_ground_a_warm_up():
    assert "warmup" not in ids(make_plan(cv_lines=["이력서에 없는 가짜 경력 한 줄입니다 정말로"]))


def test_a_bank_question_that_quotes_the_cv_can_be_the_warm_up():
    quote = "Python, FastAPI로 추천 API 설계 및 팀 리드"
    plan = make_plan(questions=[q("추천 API를 설계할 때 팀을 어떻게 이끄셨나요?", None, "experience", quote)], cv_lines=[])
    assert plan.items[0].topic_id == "warmup" and plan.items[0].cv_quote == quote


def test_evidence_lines_skip_headings_contacts_and_placeholders():
    lines = evidence_lines(
        ["경력\n- Java, Spring Boot 기반 주문 API 개발\n이메일: [이메일]\n김지원 [이름] 담당 팀 리드 경험입니다\n짧음\n학력\n한국대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02"]
    )
    assert "Java, Spring Boot 기반 주문 API 개발" in lines
    assert lines[0] == "Java, Spring Boot 기반 주문 API 개발"  # bullet lines first
    assert all("[" not in line and line not in ("경력", "학력", "짧음") for line in lines)


@pytest.mark.parametrize("item_index", range(5))
def test_every_item_has_two_to_four_ai_generated_rubric_points(item_index):
    plan = make_plan()
    item = plan.items[item_index]
    assert 2 <= len(item.rubric) <= 4
    assert [p.id for p in item.rubric] == [f"p{n}" for n in range(1, len(item.rubric) + 1)]
    assert all(p.source == AI_GENERATED and p.keywords and p.text for p in item.rubric)
    assert plan.rubric_notice == RUBRIC_NOTICE and "기업의 요구사항이 아닙니다" in plan.rubric_notice


def test_rubric_points_come_from_the_criterion_description_first():
    java = make_plan().items[1]
    assert [p.text for p in java.rubric] == ["Java 17", "Spring Boot 사용 경험"]
    assert "java" in java.rubric[0].keywords and "spring" in java.rubric[1].keywords  # dictionary skills become cues


def test_no_weight_exists_anywhere_in_the_plan():
    for cls in (PlanCriterion, PlanItem, RubricPoint, InterviewPlan):
        assert not [f.name for f in dataclasses.fields(cls) if "weight" in f.name.lower()], cls
    assert "weight" not in json.dumps(make_plan().to_dict(), ensure_ascii=False).lower()
    assert {i.importance for i in make_plan().items if i.importance} <= {"핵심", "중요", "일반"}  # labels only, never numbers


def test_a_weight_passed_as_the_importance_is_rejected():
    with pytest.raises(ValueError, match="importance"):
        build_plan([PlanCriterion(1, "Java", "skill", "", "30")], (), MASKED_CV, (), BLOCKLISTS)  # type: ignore[arg-type]


def test_no_two_questions_of_a_plan_are_alike():
    # Two education criteria: the D21 template does not depend on the name, so the second needs its own wording
    criteria = [crit(1, "전공 일치", "education", "컴퓨터공학", "핵심"), crit(2, "관련 학과", "education", "소프트웨어", "핵심")]
    questions = [i.question for i in make_plan(criteria).items]
    assert len(questions) == len(set(questions)) and len(questions) >= 4


def test_bank_questions_are_reused_and_screened_ones_replaced():
    bank = [
        q("Java를 실무에서 가장 어렵게 썼던 순간은 언제인가요?", 1, depth=2),
        q("결혼 계획이 프로젝트 일정에 영향을 주나요?", 2, depth=2),  # protected topic: the interview blocklist rejects it
        q("팀에서 갈등을 조율한 경험을 말씀해 주세요.", None, "behavioral"),
    ]
    plan = make_plan(questions=bank)
    by_topic = {i.topic_id: i for i in plan.items}
    assert by_topic["c1"].question == bank[0].question  # the bank question, unchanged
    assert "결혼" not in by_topic["c2"].question and by_topic["c2"].question  # replaced by the D21 template
    assert by_topic["behavioral"].question == bank[2].question
    assert all("결혼" not in i.question for i in plan.items)


def test_without_a_bank_the_d21_templates_are_the_questions():
    info = CriterionInfo(1, "Java 활용 능력", "skill", "Java 17, Spring Boot 사용 경험")
    expected = [x for x in interview_rules([info], BLOCKLISTS) if x.criterion_id == 1 and x.depth == 2][0].question
    assert make_plan().items[1].question == expected


def test_a_criterion_whose_own_name_is_blocked_has_no_question_and_is_reported():
    criteria = [*CRITERIA, crit(9, "결혼 여부", "other", "", "핵심")]
    plan = make_plan(criteria)
    assert "c9" not in ids(plan)
    assert any(u.criterion_id == 9 and u.reason == "no_question" for u in plan.uncovered)


def test_the_plan_survives_a_round_trip_through_json():
    plan = make_plan(bank_method="llm:fake")
    restored = InterviewPlan.from_dict(json.loads(json.dumps(plan.to_dict(), ensure_ascii=False)))
    assert restored == plan and restored.bank_method == "llm:fake"


def test_an_empty_job_still_gets_a_plan_without_crashing():
    plan = make_plan(criteria=[], cv_lines=[])
    assert ids(plan) == ["behavioral"] and plan.uncovered == ()


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_build_plan_picks_the_requested_depth_and_keeps_general_questions_untagged(depth):
    bank = [
        q(f"depth-{d}-java", 1, "technical", depth=d)
        for d in (1, 2, 3)
    ] + [q("일반 협업 경험", None, "behavioral", depth=depth)]  # general depth must be ignored
    plan = make_plan(questions=bank, depth=depth)
    by_topic = {i.topic_id: i for i in plan.items}
    assert plan.depth == depth
    assert by_topic["c1"].question == f"depth-{depth}-java" and by_topic["c1"].depth == depth
    c2_template = [x for x in interview_rules([CriterionInfo(2, "프로젝트 경험", "project", "REST API를 설계하고 문서화한 경험")], BLOCKLISTS) if x.criterion_id == 2 and x.depth == depth][0]
    assert by_topic["c2"].question == c2_template.question and by_topic["c2"].depth == depth
    assert by_topic["warmup"].depth is None
    assert by_topic["behavioral"].depth is None
    # Deterministic across criterion arrival order
    assert make_plan(criteria=list(reversed(CRITERIA)), questions=bank, depth=depth).to_dict() == plan.to_dict()


def test_build_plan_depth_fallback_order():
    # Candidate order for requested depth=3:
    # bank(3) -> template(3) -> bank(2) -> template(2) -> bank(1) -> template(1) -> untagged bank -> neutral fallback
    c1 = crit(1, "Java 활용 능력", "skill", "Java 17", "핵심")
    info1 = CriterionInfo(1, "Java 활용 능력", "skill", "Java 17")
    tmpls = {x.depth: x for x in interview_rules([info1], BLOCKLISTS) if x.criterion_id == 1}

    # 1. Requested bank(3) wins over template(3)
    plan1 = make_plan(criteria=[c1], questions=[q("bank-d3", 1, depth=3), q("bank-d2", 1, depth=2)], cv_lines=[], depth=3)
    item1 = next(i for i in plan1.items if i.topic_id == "c1")
    assert item1.question == "bank-d3" and item1.depth == 3

    # 2. Missing bank(3) (or blocked bank(3)) -> template(3) wins over bank(2)
    plan2 = make_plan(criteria=[c1], questions=[q("결혼 질문", 1, depth=3), q("bank-d2", 1, depth=2)], cv_lines=[], depth=3)
    item2 = next(i for i in plan2.items if i.topic_id == "c1")
    assert item2.question == tmpls[3].question and item2.depth == 3

    # 3. For requested depth=1, when bank(1) is missing -> template(1) beats bank(2)
    plan3 = make_plan(criteria=[c1], questions=[q("bank-d2", 1, depth=2)], cv_lines=[], depth=1)
    item3 = next(i for i in plan3.items if i.topic_id == "c1")
    assert item3.question == tmpls[1].question and item3.depth == 1

    # 4. If template(d) and nearest template are eliminated by duplicate check, bank/template of nearest depth (2 first) follows in order
    dup_c = [
        crit(1, "전공 일치", "education", "컴퓨터공학", "핵심"),
        crit(2, "관련 학과", "education", "소프트웨어", "핵심"),
    ]
    plan_dup = make_plan(criteria=dup_c, questions=[q("d2-backup", 2, depth=2)], cv_lines=[], depth=3)
    c1_item = next(i for i in plan_dup.items if i.topic_id == "c1")
    c2_item = next(i for i in plan_dup.items if i.topic_id == "c2")
    # c1 takes template(3); c2 cannot reuse template(3) (education templates share wording), so it tries bank(3)->None, template(3)->dup, bank(2)->"d2-backup"
    assert c1_item.depth == 3 and c2_item.question == "d2-backup" and c2_item.depth == 2

    # 5. For depth=1 without c2 backup, duplicate template(1) falls back to nearest depth=2 template first, then depth=3
    plan_dup_1 = make_plan(criteria=dup_c, questions=[], cv_lines=[], depth=1)
    c1_1 = next(i for i in plan_dup_1.items if i.topic_id == "c1")
    c2_1 = next(i for i in plan_dup_1.items if i.topic_id == "c2")
    assert (c1_1.depth, c2_1.depth) == (1, 2)


def test_build_plan_rejects_invalid_depth_and_loads_legacy_plan_without_depth():
    for bad in (0, 4, "2", True):
        with pytest.raises(ValueError, match="depth"):
            make_plan(depth=bad)  # type: ignore[arg-type]

    plan = make_plan(depth=3)
    legacy = json.loads(json.dumps(plan.to_dict(), ensure_ascii=False))
    legacy.pop("depth")
    for item in legacy["items"]:
        item.pop("depth")
    restored = InterviewPlan.from_dict(legacy)
    assert restored.depth == 2
    assert all(item.depth is None for item in restored.items)
