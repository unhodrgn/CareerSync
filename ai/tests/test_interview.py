"""Interview questions (D21): template, LLM output checks (criterion ids, CV quotes, both blocklists, URLs), fallbacks."""
from pathlib import Path

import pytest

from ai.career.interview import (
    DEPTHS,
    MAX_BANK_QUESTIONS,
    MAX_EXCERPTS,
    MAX_QUESTIONS,
    CriterionInfo,
    allowed,
    cv_excerpts,
    interview_rules,
    make_questions,
)
from ai.guardrails.blocklist import load_blocklist
from ai.interview.guards import screen_spoken
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


def _q(question, criterion_id=None, kind="technical", cv_quote=None, intent="확인", tips=("구체적으로",), depth=None):
    return {"question": question, "criterion_id": criterion_id, "kind": kind, "intent": intent,
            "answer_tips": list(tips), "cv_quote": cv_quote, "depth": depth}


def _make(llm, **kwargs):
    return make_questions("백엔드 개발자", "Java, Spring 기반 API 개발", CRITERIA, MASKED, EMBEDDER, BLOCKLISTS, llm, **kwargs)


# ── Template ──


def test_template_has_a_question_per_criterion_and_general_ones():
    qs = interview_rules(CRITERIA, BLOCKLISTS)
    assert [q.criterion_id for q in qs[:12]] == [11, 11, 11, 12, 12, 12, 13, 13, 13, 14, 14, 14]
    assert [q.depth for q in qs[:12]] == [1, 2, 3] * 4
    assert qs[0].kind == "technical" and qs[9].kind == "behavioral"
    assert [q.criterion_id for q in qs[12:]] == [None, None, None]
    assert [q.depth for q in qs[12:]] == [None, None, None]
    assert all(q.cv_quote is None and q.answer_tips for q in qs)
    general_only = interview_rules([], BLOCKLISTS)
    assert len(general_only) == 3 and all(q.depth is None for q in general_only)
    many = [CriterionInfo(i, f"기술 {i}", "skill") for i in range(20)]
    assert len(interview_rules(many, BLOCKLISTS)) == MAX_BANK_QUESTIONS
    single = interview_rules(many, BLOCKLISTS, depths=(2,), max_questions=MAX_QUESTIONS)
    assert len(single) == MAX_QUESTIONS and all(q.depth == 2 for q in single)


@pytest.mark.parametrize("category", ["skill", "experience", "project", "certificate", "education", "other"])
def test_template_has_three_screened_depths_per_category_and_is_deterministic(category):
    criterion = [CriterionInfo(1, "Python 백엔드", category, "FastAPI 경험")]
    first = interview_rules(criterion, BLOCKLISTS)
    second = interview_rules(criterion, BLOCKLISTS)
    assert first == second
    by_depth = [q for q in first if q.criterion_id == 1]
    assert [q.depth for q in by_depth] == list(DEPTHS)
    assert len({q.question for q in by_depth}) == 3
    assert len({q.answer_tips for q in by_depth}) == 3
    for q in by_depth:
        assert allowed(q.question, q.intent, q.answer_tips, BLOCKLISTS)
        assert screen_spoken(q.question, BLOCKLISTS, "question") is not None


# ── LLM ──


def test_llm_questions_are_checked():
    llm = FakeLLM({"questions": [
        _q("Java 17의 주요 변경점을 설명해 주세요.", 11, depth=1),
        _q("주문 API를 개발할 때 어떤 설계 결정을 했나요?", 12, "experience", cv_quote=QUOTE, depth=2),
        _q("Kubernetes 클러스터를 운영해 본 경험이 있나요?", 999, cv_quote="Kubernetes 운영 3년", depth=3),  # bad id -> None, depth dropped
        _q("나이가 어떻게 되시나요?", None, "behavioral"),  # protected attribute: dropped
        _q("부모님 직업은 무엇인가요?", None, "behavioral"),  # dropped
        _q("코드 리뷰에서 의견 충돌을 어떻게 해결했나요?", 14, "behavioral", tips=("자세한 내용은 https://example.com/guide 참고",), depth=3),
        _q("Java 17의 주요 변경점을 설명해 주세요.", 11, depth=1),  # duplicate
    ]})
    questions, method = _make(llm, fill_missing=False)
    assert method == "llm:fake-llm"
    assert [(q.criterion_id, q.depth) for q in questions] == [(11, 1), (12, 2), (None, None), (14, 3)]
    assert questions[1].cv_quote == QUOTE and questions[1].criterion_name == "프로젝트 경험"
    assert questions[2].cv_quote is None  # not in the CV
    assert questions[3].answer_tips == ("자세한 내용은 참고",)
    assert not any("나이" in q.question or "부모님" in q.question for q in questions)


def test_llm_depth_validation_missing_fill_and_d21_single_depth():
    llm = FakeLLM({"questions": [
        _q("Java 핵심 개념은 무엇인가요?", 11, depth=1),
        _q("잘못된 깊이 4가 온 질문입니다.", 12, depth=4),       # invalid depth -> None
        _q("잘못된 문자열 깊이 질문입니다.", 12, depth="bad"), # invalid depth -> None
        _q("불리언 깊이 질문입니다.", 13, depth=True),         # bool True -> None
        _q("일반 인성 질문에 depth가 온 경우", None, "behavioral", depth=2),  # general -> depth dropped
        _q("미등록 기준에 depth가 온 경우", 999, depth=3),                  # invalid cid -> cid None, depth dropped
    ]})
    questions, method = _make(llm)
    assert method == "llm:fake-llm"
    assert (11, 1) in {(q.criterion_id, q.depth) for q in questions}
    assert "Java 핵심 개념은 무엇인가요?" in {q.question for q in questions}
    # Invalid depths on LLM items kept as None; general/bad cid dropped depth to None
    invalid_tagged = [q for q in questions if q.question in {
        "잘못된 깊이 4가 온 질문입니다.", "잘못된 문자열 깊이 질문입니다.", "불리언 깊이 질문입니다.",
        "일반 인성 질문에 depth가 온 경우", "미등록 기준에 depth가 온 경우",
    }]
    assert all(q.depth is None for q in invalid_tagged)
    # Missing (criterion_id, depth) pairs filled deterministically from templates
    tmpl_pairs = {(q.criterion_id, q.depth) for q in questions if q.criterion_id is not None and q.depth is not None}
    expected_pairs = {(c.id, d) for c in CRITERIA for d in DEPTHS}
    assert expected_pairs <= tmpl_pairs

    # Caller like D21 text feature asks for single depth 2, no template fill, capped at MAX_QUESTIONS (10)
    full_bank = [
        _q(f"c{c.id}-d{d}", c.id, "technical", depth=d)
        for c in CRITERIA for d in DEPTHS
    ] + [_q("일반 질문", None, "behavioral", depth=2)]
    d21_qs, _ = _make(
        FakeLLM({"questions": full_bank}),
        depths=(2,), fill_missing=False, max_questions=MAX_QUESTIONS, single_depth=2,
    )
    assert [q.question for q in d21_qs] == ["c11-d2", "c12-d2", "c13-d2", "c14-d2", "일반 질문"]
    assert d21_qs[-1].depth is None


def test_a_protected_topic_in_the_tips_drops_the_question():
    llm = FakeLLM({"questions": [
        _q("팀워크 경험을 말해 주세요.", 14, "behavioral", tips=("결혼 여부와 함께 소개하기",)),
        _q("A", 11), _q("B", 12), _q("C", 13),
    ]})
    questions, _ = _make(llm, fill_missing=False)
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


class _ErrorLLM:
    """A model whose error message quotes the model's output, the way a validation error does (the marker stands for a CV line)."""

    model = "error-llm"

    def __init__(self, error):
        self.error = error

    def complete_json(self, system, user, schema, max_tokens=4000):
        raise self.error


def test_a_failed_llm_call_logs_the_error_type_only_and_the_fallback_is_unchanged(caplog):
    """D65: the message of an LLM error can quote the model's output, which can quote CV lines. Nothing but the type is logged."""
    import logging

    from ai.llm.client import LLMError

    secret = "SECRET-CV-LINE-김지원-2019년-입사"
    error = LLMError(f"LLM output failed validation: 1 validation error, input_value='{secret}'")
    error.__cause__ = ValueError(secret)  # a traceback would print this too
    caplog.set_level(logging.DEBUG)
    questions, method = _make(_ErrorLLM(error))
    assert method == "rules" and questions == interview_rules(CRITERIA, BLOCKLISTS)  # the fallback is what it was
    (record,) = [r for r in caplog.records if "using the template" in r.getMessage()]
    assert (record.levelno, record.args, record.exc_info) == (logging.WARNING, ("LLMError",), None)
    assert secret not in caplog.text and "input_value" not in caplog.text


DROPPED_MARKER = "SECRET-DROPPED-QUESTION-김지원-2019년-입사"


def _dropped_logs(caplog):
    return [r for r in caplog.records if "question dropped" in r.getMessage()]


def test_a_dropped_template_question_logs_a_reason_and_never_its_text(caplog):
    """D65: a dropped question is logged by reason, source and criterion id. Its text (here it holds a marker, and a blocked word that
    makes the blocklist drop it) can quote the CV, so it is not logged."""
    import logging

    caplog.set_level(logging.DEBUG)
    criteria = [*CRITERIA, CriterionInfo(21, f"{DROPPED_MARKER} 결혼 여부", "other")]
    questions = interview_rules(criteria, BLOCKLISTS)
    assert all(DROPPED_MARKER not in q.question for q in questions)  # the question of criterion 21 was dropped, and the others are as before
    assert [q.criterion_id for q in questions[:12]] == [11, 11, 11, 12, 12, 12, 13, 13, 13, 14, 14, 14] and 21 not in {q.criterion_id for q in questions}
    records = _dropped_logs(caplog)
    assert len(records) == 3 and {r.getMessage() for r in records} == {"interview question dropped: reason=blocklist source=template criterion_id=21"}
    assert all(r.levelno == logging.INFO and r.exc_info is None for r in records)
    assert DROPPED_MARKER not in caplog.text and "결혼" not in caplog.text


def test_a_dropped_llm_question_logs_a_reason_and_never_its_text_and_the_result_is_unchanged(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    llm = FakeLLM({"questions": [
        _q(f"{DROPPED_MARKER} 나이가 어떻게 되시나요?", 11),  # dropped by a blocklist, for a real criterion
        _q(f"{DROPPED_MARKER} 가족 계획이 있나요?", 999),  # dropped, for a criterion that does not exist: no id is logged
        _q("Java를 써 봤나요?", 11), _q("Spring은요?", 12), _q("협업은 어땠나요?", 14),
    ]})
    questions, method = _make(llm, fill_missing=False)
    assert method.startswith("llm:") and [q.question for q in questions] == ["Java를 써 봤나요?", "Spring은요?", "협업은 어땠나요?"]
    assert sorted(r.getMessage() for r in _dropped_logs(caplog)) == [
        "interview question dropped: reason=blocklist source=llm criterion_id=11",
        "interview question dropped: reason=blocklist source=llm criterion_id=None",
    ]
    assert all(r.exc_info is None and r.levelno == logging.INFO for r in _dropped_logs(caplog))
    assert DROPPED_MARKER not in caplog.text and "나이가" not in caplog.text and "가족" not in caplog.text


def test_when_dropped_questions_leave_too_few_the_template_is_used_and_no_text_is_logged(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    llm = FakeLLM({"questions": [
        _q(f"{DROPPED_MARKER} 나이가 어떻게 되시나요?", 11), _q(f"{DROPPED_MARKER} 결혼은 하셨나요?", 12), _q("Java를 써 봤나요?", 11),
    ]})
    questions, method = _make(llm)
    assert method == "rules" and questions == interview_rules(CRITERIA, BLOCKLISTS)  # the fallback is what it was
    assert len(_dropped_logs(caplog)) == 2
    assert [r.getMessage() for r in caplog.records if "using the template" in r.getMessage()] == ["interview questions by LLM failed, using the template: LLMError"]
    assert DROPPED_MARKER not in caplog.text and "나이가" not in caplog.text and "결혼은" not in caplog.text


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
    questions, method = _make(llm, fill_missing=False)
    assert method == "llm:fake-llm"
    assert [q.question for q in questions] == ["Spring에서 트랜잭션을 어떻게 처리했나요?", "A", "B"]


def test_template_questions_are_screened_too():
    criteria = [*CRITERIA, CriterionInfo(15, "가족 같은 팀워크", "other")]
    questions = interview_rules(criteria, BLOCKLISTS)
    assert 15 not in {q.criterion_id for q in questions}
    assert all(allowed(q.question, q.intent, q.answer_tips, BLOCKLISTS) for q in questions)
    assert len(questions) >= 3
