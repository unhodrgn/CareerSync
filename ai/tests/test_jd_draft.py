"""JD drafts: template, LLM output screening and fallbacks (docs/DECISIONS.md D24)."""
from pathlib import Path

import pytest

from ai.embedding.skills import load_dictionary
from ai.guardrails.blocklist import load_blocklist
from ai.jd.draft import (
    MAX_ITEMS,
    REASON_CONTACT,
    REASON_LENGTH,
    REASON_MONEY,
    DraftInput,
    JdDraft,
    ProjectInfo,
    drop_reason,
    draft_rules,
    make_draft,
    screen,
)
from ai.llm.client import LLMError
from ai.parsing.extract import analyze_jd_rules
from ai.tests.helpers import FakeLLM

DATA = Path(__file__).resolve().parents[2] / "data"
BLOCKLIST = load_blocklist(DATA / "blocklist.yaml")
SKILLS = load_dictionary(DATA / "skills.yaml")

INPUT = DraftInput(
    title="백엔드 개발자",
    employment_type="full_time",
    min_experience_years=3,
    keywords=("java", "Spring", "MSA"),
    notes="결제팀 백엔드",
    company_name="Acme",
    company_intro="B2B 결제 SaaS",
    talent_profile="주도적으로 문제를 정의하는 사람",
    projects=(ProjectInfo("결제 시스템 MSA 전환", "모놀리식 결제 서버 분리", ("Kafka", "Java")),),
)

LLM_DRAFT = {
    "intro": "Acme 결제팀에서 결제 시스템 MSA 전환을 함께할 백엔드 개발자를 찾습니다.",
    "responsibilities": ["- 결제 API 설계 및 개발", "Kafka 기반 이벤트 처리", "결제 API 설계 및 개발"],
    "requirements": ["Java/Spring 실무 경력 3년 이상", "남성 지원자 우대", "연봉 5,000만 원 이상 협의 가능"],
    "preferred": ["MSA 전환 경험", "문의: hr@acme.example", "자세한 내용은 https://acme.example/jobs 참고"],
}


@pytest.mark.parametrize(
    "text, reason",
    [
        ("연봉 협의", REASON_MONEY),
        ("초봉 4,000만 원 이상", REASON_MONEY),
        ("월 300만원 지급", REASON_MONEY),
        ("성과급 및 인센티브 제공", REASON_MONEY),
        ("$100 bonus", REASON_MONEY),
        ("문의: hr@acme.co.kr", REASON_CONTACT),
        ("지원: 02-1234-5678", REASON_CONTACT),
        ("연락처 010 1234 5678", REASON_CONTACT),
        ("https://acme.example 참고", REASON_CONTACT),
        ("www.acme.com 방문", REASON_CONTACT),
        ("acme.com/careers 에서 지원", REASON_CONTACT),
    ],
)
def test_pay_and_contacts_are_dropped(text, reason):
    assert drop_reason(text, BLOCKLIST) == reason


@pytest.mark.parametrize("text", ["남성 우대", "30세 이하", "미혼자 우대", "용모 단정한 분", "키 170cm 이상", "서울 출신 우대"])
def test_blocklist_hits_are_dropped_with_the_law(text):
    reason = drop_reason(text, BLOCKLIST)
    assert reason and "(" in reason  # rule reason plus law_ref


@pytest.mark.parametrize(
    "text",
    [
        "Java/Spring 기반 백엔드 API 개발",
        "Node.js 또는 Socket.io 사용 경험",
        "일 5억 건 이상의 트래픽 처리 경험",
        "SOLID 3원칙 이해",
        "유지보수하기 쉬운 코드 작성",
        "장애 대응 및 운영 경험",
        "관련 경력 3년 이상",
        "신입 지원 가능",
    ],
)
def test_job_sentences_pass(text):
    assert drop_reason(text, BLOCKLIST) is None


def test_template_uses_the_inputs():
    d = screen(draft_rules(INPUT, SKILLS), BLOCKLIST)
    assert "Acme" in d.intro and "정규직" in d.intro and "결제팀 백엔드" in d.intro
    assert any("결제 시스템 MSA 전환" in r and "Kafka" in r for r in d.responsibilities)
    assert d.requirements[0] == "관련 경력 3년 이상"
    assert "Java 실무 또는 프로젝트 경험" in d.requirements  # keyword normalized
    assert "Kafka 사용 경험" in d.preferred and not any("Java 사용" in p for p in d.preferred)
    assert not d.dropped


def test_template_without_years_or_keywords():
    d = draft_rules(DraftInput(title="데이터 엔지니어", min_experience_years=None), SKILLS)
    assert d.requirements[0] == "신입 지원 가능"
    assert "데이터 엔지니어 직무 관련 지식과 경험" in d.requirements
    assert draft_rules(DraftInput(title="x", min_experience_years=0), SKILLS).requirements[0] == "신입 지원 가능"


def test_template_is_screened_too():
    # The criteria blocklist matches "남성" only with a hiring word ("우대", "지원자"…)
    inp = DraftInput(title="개발자", keywords=("Java", "남성 우대"), notes="연봉 6천만원")
    d, method = make_draft(inp, SKILLS, BLOCKLIST, None)
    assert method == "rules"
    assert not any("남성" in r for r in d.requirements) and "6천만원" not in d.intro
    assert {x.reason for x in d.dropped} >= {REASON_MONEY}
    assert any("남성" in x.text for x in d.dropped)


def test_description_lists_sections_in_order_for_analyze_jd():
    d = screen(draft_rules(INPUT, SKILLS), BLOCKLIST)
    text = d.description
    assert text.index("주요 업무") < text.index("자격 요건") < text.index("우대 사항")
    assert "- 관련 경력 3년 이상" in text
    # analyze_jd reads requirements before "우대": the draft round-trips into criteria suggestions
    analysis = analyze_jd_rules(INPUT.title, text, None, SKILLS)
    assert "Java" in analysis.profile.required_skills and analysis.profile.min_years == 3


def test_llm_draft_is_screened():
    llm = FakeLLM(LLM_DRAFT)
    d, method = make_draft(INPUT, SKILLS, BLOCKLIST, llm)
    assert method == "llm:fake-llm"
    assert d.responsibilities == ["결제 API 설계 및 개발", "Kafka 기반 이벤트 처리"]  # bullet stripped, duplicate dropped
    assert d.requirements == ["Java/Spring 실무 경력 3년 이상"]
    assert d.preferred == ["MSA 전환 경험"]
    reasons = {x.text: x.reason for x in d.dropped}
    assert reasons["연봉 5,000만 원 이상 협의 가능"] == REASON_MONEY
    assert reasons["문의: hr@acme.example"] == REASON_CONTACT
    assert "남성 지원자 우대" in reasons
    # The LLM saw company data only, with tags
    system, user = llm.calls[0]
    assert "<projects>" in user and "결제 시스템 MSA 전환" in user and "<keywords>" in user
    assert "Never invent salary" in system


def test_long_and_extra_items():
    d = screen(
        JdDraft(intro="", responsibilities=[f"업무 {i}" for i in range(12)], requirements=["가" * 201, "Java"], preferred=[]),
        BLOCKLIST,
    )
    assert len(d.responsibilities) == MAX_ITEMS and d.requirements == ["Java"]
    assert [x.reason for x in d.dropped] == [REASON_LENGTH]


def test_llm_error_falls_back_to_the_template():
    d, method = make_draft(INPUT, SKILLS, BLOCKLIST, FakeLLM(LLMError("down")))
    assert method == "rules" and d.requirements[0] == "관련 경력 3년 이상"


def test_no_requirements_left_falls_back_to_the_template():
    bad = {**LLM_DRAFT, "requirements": ["남성 우대", "연봉 협의"]}
    d, method = make_draft(INPUT, SKILLS, BLOCKLIST, FakeLLM(bad))
    assert method == "rules" and d.requirements
    assert not any("남성" in r for r in d.requirements)
