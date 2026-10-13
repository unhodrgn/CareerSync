"""Interview questions (D21): template, LLM output checks (criterion ids, CV quotes, guardrail, URLs), fallbacks."""
from pathlib import Path

import pytest

from ai.career.interview import MAX_EXCERPTS, MAX_QUESTIONS, CriterionInfo, cv_excerpts, interview_rules, make_questions
from ai.guardrails.blocklist import load_blocklist
from ai.parsing.pii import mask_pii
from ai.tests.helpers import EMBEDDER, SAMPLE_CV, FakeLLM

BLOCKLIST = load_blocklist(Path(__file__).resolve().parents[2] / "data" / "blocklist.yaml")
MASKED = mask_pii(SAMPLE_CV, ["김지원"]).text
CRITERIA = [
    CriterionInfo(11, "Java 활용 능력", "skill", "Java 17"),
    CriterionInfo(12, "프로젝트 경험", "project", "API 설계"),
    CriterionInfo(13, "관련 전공", "education"),
    CriterionInfo(14, "협업 태도", "other", "코드 리뷰 문화"),
]
QUOTE = "- Java, Spring Boot 기반 주문 API 개발"


def _q(question, criterion_id=None, kind="technical", cv_quote=None, intent="확인", tips=("구체적으로",)):
    return {"question": question, "criterion_id": criterion_id, "kind": kind, "intent": intent,
            "answer_tips": list(tips), "cv_quote": cv_quote}


def _make(llm):
    return make_questions("백엔드 개발자", "Java, Spring 기반 API 개발", CRITERIA, MASKED, EMBEDDER, BLOCKLIST, llm)


# ── Template ──


def test_template_has_a_question_per_criterion_and_general_ones():
    qs = interview_rules(CRITERIA)
    assert [q.criterion_id for q in qs[:4]] == [11, 12, 13, 14]
    assert qs[0].question.startswith("Java 활용 능력을(를)") and qs[0].kind == "technical"
    assert qs[3].kind == "behavioral" and qs[4].criterion_id is None
    assert all(q.cv_quote is None and q.answer_tips for q in qs)
    assert len(interview_rules([])) == 3  # general questions only
    many = [CriterionInfo(i, f"기술 {i}", "skill") for i in range(20)]
    assert len(interview_rules(many)) == MAX_QUESTIONS


# ── LLM ──


def test_llm_questions_are_checked():
    llm = FakeLLM({"questions": [
        _q("Java 17의 주요 변경점을 설명해 주세요.", 11),
        _q("주문 API를 개발할 때 어떤 설계 결정을 했나요?", 12, "experience", cv_quote=QUOTE),
        _q("Kubernetes 클러스터를 운영해 본 경험이 있나요?", 999, cv_quote="Kubernetes 운영 3년"),  # bad id, invented quote
        _q("나이가 어떻게 되시나요?", None, "behavioral"),  # protected attribute: dropped
        _q("부모님 직업은 무엇인가요?", None, "behavioral"),  # dropped
        _q("코드 리뷰에서 의견 충돌을 어떻게 해결했나요?", 14, "behavioral", tips=("자세한 내용은 https://example.com/guide 참고",)),
        _q("Java 17의 주요 변경점을 설명해 주세요.", 11),  # duplicate
    ]})
    questions, method = _make(llm)
    assert method == "llm:fake-llm"
    assert [q.criterion_id for q in questions] == [11, 12, None, 14]
    assert questions[1].cv_quote == QUOTE and questions[1].criterion_name == "프로젝트 경험"
    assert questions[2].cv_quote is None  # not in the CV
    assert questions[3].answer_tips == ("자세한 내용은 참고",)
    assert not any("나이" in q.question or "부모님" in q.question for q in questions)


def test_a_protected_topic_in_the_tips_drops_the_question():
    llm = FakeLLM({"questions": [
        _q("팀워크 경험을 말해 주세요.", 14, "behavioral", tips=("결혼 여부와 함께 소개하기",)),
        _q("A", 11), _q("B", 12), _q("C", 13),
    ]})
    questions, _ = _make(llm)
    assert [q.question for q in questions] == ["A", "B", "C"]


@pytest.mark.parametrize(
    "response",
    [
        None,  # LLMError: no response
        {"questions": [_q("나이가 어떻게 되시나요?"), _q("Java를 써 봤나요?", 11), _q("Spring은요?", 12)]},  # 2 left after checks
    ],
)
def test_fewer_than_three_usable_questions_fall_back_to_the_template(response):
    llm = FakeLLM(*([response] if response else []))
    questions, method = _make(llm)
    assert method == "rules" and questions == interview_rules(CRITERIA)


def test_the_llm_sees_at_most_four_masked_cv_excerpts():
    llm = FakeLLM({"questions": [_q("A", 11), _q("B", 12), _q("C", 13)]})
    _make(llm)
    (system, user), = llm.calls
    excerpts = user.split("<cv_excerpts>\n", 1)[1].split("\n</cv_excerpts>", 1)[0].split("\n---\n")
    assert 1 <= len(excerpts) <= MAX_EXCERPTS
    assert all(e in MASKED for e in excerpts)
    for secret in ("김지원", "jiwon.kim@example.com", "010-1234-5678", "테헤란로", "1997.05.12"):
        assert secret not in user
    assert "11 | Java 활용 능력 | skill | Java 17" in user and "weight" not in user


def test_excerpts_come_from_the_masked_text():
    excerpts = cv_excerpts(MASKED, "백엔드 Java API", EMBEDDER)
    assert 1 <= len(excerpts) <= MAX_EXCERPTS and all(e in MASKED for e in excerpts)
