"""Rule-based recruiter questions must be bounded and grounded in scrubbed CV quotes."""
from ai.career.interview import CriterionInfo
from ai.career.verification import evidence_candidates, generate_questions

CRITERIA = [
    CriterionInfo(1, "Java 활용 능력", "skill", "Java API"),
    CriterionInfo(2, "프로젝트 경험", "project", "Java"),
]
CV = "프로젝트\n- Java API 성능 개선 및 구현\n- Java 백엔드 서비스 개발\n"


def test_questions_have_original_cv_quotes():
    questions, method = generate_questions("Java developer", "Java Spring API 개발", CRITERIA, CV, [], None)
    assert method == "rules"
    assert 0 < len(questions) <= 3
    assert all(q.cv_quote in CV and q.criterion_id in {1, 2} for q in questions)
    assert any("측정" in q.question for q in questions)


def test_no_hallucinated_quotes():
    questions, _ = generate_questions("Java developer", "Java Spring", CRITERIA, "프로젝트\n- 사진 촬영\n", [], None)
    assert questions == []
    assert evidence_candidates("연락처: test@example.com", CRITERIA) == []


def test_quantified_and_owned_claim_is_deprioritized():
    cv = "프로젝트\n- Java API 성능을 30% 개선하고 직접 담당하여 구현\n"
    assert evidence_candidates(cv, CRITERIA) == []
