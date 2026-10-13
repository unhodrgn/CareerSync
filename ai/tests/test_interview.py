"""Interview questions (D21): template, LLM output checks (criterion ids, CV quotes, both blocklists, URLs), fallbacks."""
from pathlib import Path

import pytest

from ai.career.interview import (
    MAX_EXCERPTS,
    MAX_QUESTIONS,
    CriterionInfo,
    allowed,
    cv_excerpts,
    interview_rules,
    make_questions,
)
from ai.guardrails.blocklist import load_blocklist
from ai.parsing.pii import mask_pii
from ai.tests.helpers import EMBEDDER, SAMPLE_CV, FakeLLM

DATA = Path(__file__).resolve().parents[2] / "data"
CRITERIA_BLOCKLIST = load_blocklist(DATA / "blocklist.yaml")
INTERVIEW_BLOCKLIST = load_blocklist(DATA / "interview_blocklist.yaml")
BLOCKLISTS = [CRITERIA_BLOCKLIST, INTERVIEW_BLOCKLIST]
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
    return make_questions("백엔드 개발자", "Java, Spring 기반 API 개발", CRITERIA, MASKED, EMBEDDER, BLOCKLISTS, llm)


# ── Template ──


def test_template_has_a_question_per_criterion_and_general_ones():
    qs = interview_rules(CRITERIA, BLOCKLISTS)
    assert [q.criterion_id for q in qs[:4]] == [11, 12, 13, 14]
    assert qs[0].question.startswith("Java 활용 능력을(를)") and qs[0].kind == "technical"
    assert qs[3].kind == "behavioral" and qs[4].criterion_id is None
    assert all(q.cv_quote is None and q.answer_tips for q in qs)
    assert len(interview_rules([], BLOCKLISTS)) == 3  # general questions only
    many = [CriterionInfo(i, f"기술 {i}", "skill") for i in range(20)]
    assert len(interview_rules(many, BLOCKLISTS)) == MAX_QUESTIONS


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
    assert method == "rules" and questions == interview_rules(CRITERIA, BLOCKLISTS)


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


# ── Interview blocklist (issue 30): questions and conversation, not criterion names ──

BLOCKED = {
    "marital": ["결혼하셨나요?", "결혼했어?", "결혼 계획이 있으신가요?", "기혼이세요, 미혼이세요?", "배우자는 무슨 일을 하세요?"],
    "children": ["자녀가 있으신가요?", "아이가 있어?", "출산 계획이 있나요?", "임신 계획은 어떻게 되세요?", "육아는 누가 하나요?"],
    "dating": ["여자친구 있으세요?", "남자 친구 있어?", "애인은 있나요?", "요즘 연애하세요?"],
    "religion": ["종교가 있으신가요?", "교회 다니세요?", "무교인가요?"],
    "age": ["나이가 어떻게 되세요?", "몇 살이야?", "몇 년생이세요?", "올해 연세가 어떻게 되십니까?", "28살이면 늦은 편 아닌가요?"],
    "appearance": ["키가 몇이에요?", "몸무게는요?", "외모 관리는 어떻게 하세요?", "살을 좀 빼실 생각은 없나요?"],
    "origin": ["고향이 어디세요?", "어디 출신이야?", "사투리를 쓰시나요?"],
    "family": ["부모님은 무슨 일을 하세요?", "아버지 직업이 뭐예요?", "가족 관계를 말씀해 주세요.", "집안 형편은 어떠세요?", "재산은 어느 정도인가요?"],
    "politics": ["지지하는 정당이 있나요?", "지난 선거에서 투표하셨어요?", "정치 성향은 어떠세요?"],
    "health": ["건강 상태는 어떠세요?", "지병이 있으신가요?", "장애가 있으세요?", "복용하는 약이 있나요?", "정신과 진료를 받은 적이 있나요?"],
}
NORMAL = [
    "Spring에서 트랜잭션을 어떻게 처리했나요?",
    "장애 대응 경험을 말씀해 주세요.",
    "유지보수하기 쉬운 코드를 위해 무엇을 하나요?",
    "아이디어를 제안해 반영된 경험이 있나요?",
    "Kafka 컨슈머 그룹의 동작 방식을 설명해 주세요.",
    "API 응답 시간을 어떻게 줄였나요?",
    "코드 리뷰에서 피드백을 주고받은 경험은요?",
    "MySQL 인덱스를 설계할 때 무엇을 고려하나요?",
    "팀에서 의견이 달랐던 경험과 어떻게 해결했는지 말씀해 주세요.",
    "이 회사와 직무에 지원한 이유는 무엇인가요?",
]


@pytest.mark.parametrize("question", [q for qs in BLOCKED.values() for q in qs])
def test_protected_questions_are_blocked(question):
    assert not allowed(question, "", (), BLOCKLISTS)
    assert not allowed("자기소개를 해 주세요.", question, (), BLOCKLISTS)  # in the intent
    assert not allowed("자기소개를 해 주세요.", "확인", (question,), BLOCKLISTS)  # in a tip


@pytest.mark.parametrize("question", NORMAL)
def test_normal_questions_are_not_blocked(question):
    assert allowed(question, "직무 역량 확인", ("구체적인 사례를 들어 설명하기",), BLOCKLISTS)


def test_the_interview_blocklist_runs_after_the_criteria_guardrail():
    # "결혼하셨나요?" passes data/blocklist.yaml (written for criterion names) but not the interview list
    assert allowed("결혼하셨나요?", "", (), [CRITERIA_BLOCKLIST])
    assert not allowed("결혼하셨나요?", "", (), BLOCKLISTS)


def test_llm_questions_on_protected_topics_are_dropped():
    llm = FakeLLM({"questions": [
        _q("결혼하셨나요?", None, "behavioral"),
        _q("자녀 계획이 있으세요?", None, "behavioral"),
        _q("Spring에서 트랜잭션을 어떻게 처리했나요?", 11),
        _q("팀워크 경험을 말해 주세요.", 14, "behavioral", intent="가족 같은 분위기에 맞는지 확인"),
        _q("A", 11), _q("B", 12),
    ]})
    questions, method = _make(llm)
    assert method == "llm:fake-llm"
    assert [q.question for q in questions] == ["Spring에서 트랜잭션을 어떻게 처리했나요?", "A", "B"]


def test_template_questions_are_screened_too():
    criteria = [*CRITERIA, CriterionInfo(15, "가족 같은 팀워크", "other")]
    questions = interview_rules(criteria, BLOCKLISTS)
    assert 15 not in {q.criterion_id for q in questions}
    assert all(allowed(q.question, q.intent, q.answer_tips, BLOCKLISTS) for q in questions)
    assert len(questions) >= 3
