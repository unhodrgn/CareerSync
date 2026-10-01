import pytest

from ai.parsing.extract import analyze_jd, months_between, structure_cv, total_experience_months
from ai.parsing.pdf import PdfError, extract_text
from ai.parsing.pii import mask_pii
from ai.parsing.profile import Experience
from ai.parsing.sections import split_sections
from ai.tests.helpers import SAMPLE_CV, SKILLS, FakeLLM, make_pdf


def test_pii_is_masked():
    m = mask_pii(SAMPLE_CV, ["김지원"])
    for secret in ("jiwon.kim@example.com", "010-1234-5678", "테헤란로", "1997.05.12", "김지원"):
        assert secret not in m.text
    assert set(m.masked) == {"email", "phone", "address", "birth", "name"}
    assert "Java, Spring Boot 기반 주문 API 개발" in m.text


def test_name_with_spaces_between_syllables_is_masked():
    assert "[이름]" in mask_pii("지원자: 김 지 원", ["김지원"]).text


def test_sections_by_heading():
    keys = [s.key for s in split_sections(SAMPLE_CV)]
    assert keys == ["other", "experience", "project", "education", "certificate"]


def test_rules_structure_the_sample_cv():
    profile, method = structure_cv(mask_pii(SAMPLE_CV, ["김지원"]).text, SKILLS, None)
    assert method == "rules"
    assert {"Java", "Spring", "MySQL", "Kotlin", "Redis", "Python", "FastAPI", "Docker", "AWS"} <= set(profile.skills)
    assert [(e.org, e.start, e.end) for e in profile.experiences] == [
        ("(주)넥스트코드", "2021-03", "2023-02"),
        ("에이비씨소프트", "2023-03", None),
    ]
    assert profile.projects[0].name == "쇼핑몰 추천 시스템"
    assert profile.projects[0].tech == ["Python", "FastAPI", "Docker", "AWS"]
    assert (profile.education[0].major, profile.education[0].degree) == ("컴퓨터공학과", "학사")
    assert [c.name for c in profile.certificates] == ["정보처리기사", "SQLD"]


def test_llm_structuring_is_normalized_and_falls_back_on_error():
    llm = FakeLLM({"skills": ["스프링 부트", "java", "Java"], "summary": "백엔드 개발자"})
    profile, method = structure_cv("text", SKILLS, llm)
    assert method == "llm:fake-llm"
    assert profile.skills == ["Spring", "Java"]
    # No queued response → LLMError → rules
    _, method = structure_cv(SAMPLE_CV, SKILLS, FakeLLM())
    assert method == "rules"


def test_experience_months_count_overlaps_once():
    exps = [Experience(start="2020-01", end="2020-12"), Experience(start="2020-07", end="2021-06"), Experience(start="2022-01", end=None)]
    assert total_experience_months(exps, today="2022-03") == 18 + 3
    assert months_between("2021-03", "2023-02", "2026-10") == 24


def test_pdf_text_and_limits():
    assert "백엔드" in extract_text(make_pdf(SAMPLE_CV)).text
    with pytest.raises(PdfError) as e:
        extract_text(b"not a pdf")
    assert e.value.code == "CV_NOT_PDF"
    with pytest.raises(PdfError) as e:
        extract_text(make_pdf(SAMPLE_CV, pages=6))
    assert e.value.code == "CV_TOO_MANY_PAGES"
    with pytest.raises(PdfError) as e:
        extract_text(make_pdf(" "))
    assert e.value.code == "CV_NO_TEXT"


def test_jd_rules_suggest_a_valid_criteria_draft():
    analysis, method = analyze_jd(
        "백엔드 개발자", "Java, Spring Boot, JPA 기반 API 개발. 경력 3년 이상.\n우대사항: AWS, Docker, 정보처리기사", None, SKILLS, None
    )
    assert method == "rules"
    assert analysis.profile.required_skills == ["Java", "Spring", "JPA"]
    assert analysis.profile.preferred_skills == ["AWS", "Docker"]
    assert analysis.profile.min_years == 3
    assert sum(c.weight for c in analysis.criteria) == 100
    assert {c.category for c in analysis.criteria} == {"skill", "experience", "project", "certificate"}


def test_jd_llm_weights_are_rescaled_to_100():
    llm = FakeLLM(
        {
            "profile": {"required_skills": ["java"]},
            "criteria": [
                {"name": "Java", "category": "skill", "weight": 50},
                {"name": "협업", "category": "other", "weight": 30},
                {"name": "bad", "category": "nope", "weight": 30},
            ],
        }
    )
    analysis, _ = analyze_jd("t", "jd", None, SKILLS, llm)
    assert [c.name for c in analysis.criteria] == ["Java", "협업"]
    assert sum(c.weight for c in analysis.criteria) == 100
