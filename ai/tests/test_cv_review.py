"""CV self-check: rule findings, LLM output validation and fallbacks (docs/DECISIONS.md D25)."""
from pathlib import Path

import pytest

from ai.career.cv_review import (
    MAX_LLM_ITEMS,
    CvReview,
    ReviewItem,
    combine,
    make_llm_review,
    review_rules,
    scoring_checks,
)
from ai.guardrails.blocklist import load_blocklist
from ai.llm.client import LLMError
from ai.parsing.extract import line_in_text, structure_cv_rules
from ai.parsing.profile import Certificate, CvProfile, Education
from ai.tests.helpers import SAMPLE_CV, SKILLS, FakeLLM

DATA = Path(__file__).resolve().parents[2] / "data"
BLOCKLISTS = [load_blocklist(DATA / "blocklist.yaml"), load_blocklist(DATA / "interview_blocklist.yaml")]
TODAY = "2026-10"
# The sample CV without its personal lines (the API masks them; here only the CV body matters)
TEXT = SAMPLE_CV.split("\n", 4)[4]
PROFILE = structure_cv_rules(TEXT, SKILLS)

QUOTE_1 = "- MySQL 인덱스 튜닝으로 조회 속도 40% 개선"
QUOTE_2 = "- Python, FastAPI로 추천 API 설계 및 팀 리드"


def _llm(strengths, improvements=()):
    return FakeLLM({"strengths": list(strengths), "improvements": list(improvements)})


def _item(title, detail="구체적인 내용입니다.", quote=None):
    return {"title": title, "detail": detail, "cv_quote": quote}


def test_rules_on_a_complete_cv():
    r = review_rules(TEXT, PROFILE, SKILLS, TODAY)
    titles = [s.title for s in r.strengths]
    assert "경력 기간이 명확함" in titles and "자격증 보유" in titles
    assert all(s.cv_quote and line_in_text(s.cv_quote, TEXT) for s in r.strengths)
    assert not any(i.affects_scoring for i in r.improvements)
    assert all(i.cv_quote is None or line_in_text(i.cv_quote, TEXT) for i in r.improvements)


def test_editor_only_skills_and_certificates_are_flagged():
    edited = PROFILE.model_copy(
        update={
            "skills": [*PROFILE.skills, "Kubernetes"],
            "certificates": [*PROFILE.certificates, Certificate(name="AWS SAA")],
        }
    )
    found = {i.title: i for i in scoring_checks(TEXT, edited, SKILLS)}
    assert "Kubernetes" in found["이력서 원문에 없는 기술"].detail
    assert "Java" not in found["이력서 원문에 없는 기술"].detail
    assert "AWS SAA" in found["이력서 원문에 없는 자격증"].detail
    assert all(i.affects_scoring for i in found.values())


def test_missing_headings_and_unreadable_periods():
    text = "경력\n넥스트코드 백엔드 개발자 (2년간 근무)\n- Java로 주문 API 개발\n"
    found = {i.title: i for i in scoring_checks(text, CvProfile(), SKILLS)}
    assert "'프로젝트' 제목 없음" in found and "'경력' 제목 없음" not in found
    assert found["경력 기간을 읽을 수 없음"].cv_quote == "넥스트코드 백엔드 개발자 (2년간 근무)"
    no_headings = {i.title for i in scoring_checks("Java 개발 5년", CvProfile(), SKILLS)}
    assert {"'경력' 제목 없음", "'프로젝트' 제목 없음"} <= no_headings


def test_major_and_project_technologies():
    text = "학력\n한국대학교 학사 2015.03 ~ 2021.02\n\n프로젝트\n동아리 홈페이지 2020.01 ~ 2020.06\n- 회원 게시판 제작\n"
    profile = CvProfile(education=[Education(school="한국대학교", major="컴퓨터공학과", source="한국대학교 학사 2015.03 ~ 2021.02")])
    found = {i.title: i for i in scoring_checks(text, profile, SKILLS)}
    # The edited major is not on the CV line, so scoring cannot read it
    assert "전공을 확인할 수 없음" in found
    assert found["기술 스택이 없는 프로젝트"].cv_quote == "동아리 홈페이지 2020.01 ~ 2020.06"


def test_llm_strengths_need_a_verified_quote():
    llm = _llm(
        [
            _item("성능 개선 경험", "인덱스 튜닝 결과가 수치로 드러납니다.", QUOTE_1),
            _item("리더십", "팀을 이끈 경험이 있습니다.", QUOTE_2),
            _item("대규모 트래픽", "하루 1억 건을 처리했습니다.", "- 하루 1억 건 트래픽 처리"),  # not in the CV
            _item("수상 경력", "수상 경력이 있습니다.", None),
        ],
        [
            _item("역할 구체화", "프로젝트에서 맡은 역할을 더 적어 보세요.", "- 지어낸 줄"),
            _item("자기소개 추가", "짧은 자기소개를 추가하세요. https://example.com/guide 참고"),
        ],
    )
    part, method = make_llm_review(TEXT, BLOCKLISTS, llm)
    assert method == "llm:fake-llm"
    assert [s.title for s in part.strengths] == ["성능 개선 경험", "리더십"]
    assert [s.cv_quote for s in part.strengths] == [QUOTE_1, QUOTE_2]
    assert part.improvements[0].cv_quote is None  # quote not in the CV
    assert "https" not in part.improvements[1].detail
    assert not any(i.affects_scoring for i in [*part.strengths, *part.improvements])
    _, user = llm.calls[0]
    assert user == f"<cv>\n{TEXT}\n</cv>"  # the CV text only


@pytest.mark.parametrize(
    "title, detail",
    [
        ("나이 기재", "나이를 적으면 좋습니다."),
        ("가족 사항", "가족 관계를 적어 보세요."),
        ("결혼 여부", "결혼하셨다면 적어 주세요."),
        ("종교 활동", "교회 봉사 경험을 강조하세요."),
        ("건강 상태", "건강 상태를 적으세요."),
    ],
)
def test_items_on_protected_topics_are_dropped(title, detail):
    llm = _llm([_item("성능 개선 경험", "수치가 있습니다.", QUOTE_1), _item(title, detail, QUOTE_2)], [_item(title, detail)])
    part, _ = make_llm_review(TEXT, BLOCKLISTS, llm)
    assert [s.title for s in part.strengths] == ["성능 개선 경험"] and part.improvements == ()


def test_at_most_five_items_each():
    many = [_item(f"강점 {i}", "내용", QUOTE_1) for i in range(8)]
    part, _ = make_llm_review(TEXT, BLOCKLISTS, _llm(many, [_item(f"개선 {i}") for i in range(8)]))
    assert len(part.strengths) == MAX_LLM_ITEMS and len(part.improvements) == MAX_LLM_ITEMS


def test_llm_error_or_no_valid_strength_returns_none():
    assert make_llm_review(TEXT, BLOCKLISTS, FakeLLM(LLMError("down"))) == (None, "rules")
    assert make_llm_review(TEXT, BLOCKLISTS, _llm([_item("지어낸 강점", "내용", "- 없는 줄")])) == (None, "rules")


def test_combine_puts_scoring_findings_first():
    edited = PROFILE.model_copy(update={"skills": [*PROFILE.skills, "Kubernetes"]})
    part = CvReview((ReviewItem("성능 개선 경험", "수치", QUOTE_1),), (ReviewItem("자기소개 추가", "짧게"),))
    r = combine(part, TEXT, edited, SKILLS)
    assert [i.title for i in r.improvements] == ["이력서 원문에 없는 기술", "자기소개 추가"]
    assert r.improvements[0].affects_scoring and r.strengths == part.strengths


def test_round_trip_through_the_cache_format():
    part = CvReview((ReviewItem("a", "b", QUOTE_1),), (ReviewItem("c", "d"),))
    assert CvReview.from_dict(part.to_dict()) == part
