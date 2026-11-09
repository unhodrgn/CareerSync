"""Required criteria gate, MVP: the job's minimum experience (docs/DECISIONS.md D50).

The CV snippets mirror the 14 matching scenarios of the local test data (test_data/ is git-ignored, so tests never
read it): TC-14 is a junior stating 0 years against a 3-year minimum, TC-02 a 5-year candidate whose REST API
criterion scores 0."""
import dataclasses
from datetime import date

import pytest

from ai.parsing.extract import StatedExperience, stated_experience, stated_experience_candidates, verified_experience
from ai.parsing.pii import mask_pii
from ai.parsing.profile import CvProfile, Experience
from ai.scoring.fit import aggregate_fit, score_candidate
from ai.scoring.gate import MIN_EXPERIENCE_SOURCE, NO_REQUIREMENT_REASON, required_gate
from ai.scoring.types import Candidate, Criterion, JobContext
from ai.tests.helpers import EMBEDDER, SAMPLE_CV, SKILLS

TODAY = "2026-11"

TC14_CV = (
    "Mã ứng viên: VN07\nVị trí mong muốn: Junior Java Developer\nSố năm kinh nghiệm: 0\n"
    "KỸ NĂNG CHUYÊN MÔN\nJava, Spring Boot, PostgreSQL, Git, Docker\n"
    "KINH NGHIỆM / CÔNG VIỆC\nDự án thực tập REST API.  unit test và SQL.\n"
    "DỰ ÁN\nỨng dụng đặt lịch với Spring Boot và PostgreSQL."
)
TC02_CV = (
    "지원 분야: 지도 서비스 백엔드 개발자\n경력: 5년\n보유 기술\nJava, Kotlin, Spring Boot, PostgreSQL, Docker, Kubernetes, Redis\n"
    "경력 및 주요 활동\n위치 기반 API 개발.  공간데이터 모델링.\n프로젝트\n경로 검색 API; PostGIS 공간인덱스와 캐시 최적화."
)


def gate(text: str, min_years: int | None, experiences: list[Experience] | None = None):
    return required_gate(text, experiences or [], min_years, TODAY)


def only_check(text: str, min_years: int, experiences: list[Experience] | None = None):
    g = gate(text, min_years, experiences)
    assert len(g.checks) == 1
    return g, g.checks[0]


# ── the 14 scenarios ──


def test_tc14_zero_stated_years_against_three_required_fails():
    g, c = only_check(TC14_CV, 3)
    assert g.status == c.status == "FAIL"
    assert (c.kind, c.source, c.required_months, c.candidate_months, c.basis) == ("min_experience", MIN_EXPERIENCE_SOURCE, 36, 0, "stated")
    assert c.evidence == ("Số năm kinh nghiệm: 0",)
    assert "최소 경력 3년에 미달" in c.reason


def test_tc02_passes_although_a_required_skill_scores_zero():
    # The gate reads no criterion and no score: REST API at 0 (missing wording) cannot cause FAIL
    criteria = [Criterion(1, "REST API", "", "skill", 50), Criterion(2, "개발 3년 이상", "", "experience", 50)]
    cand = Candidate(CvProfile(), TC02_CV)
    scores = score_candidate(criteria, cand, JobContext(title="백엔드 개발자"), skills=SKILLS, embedder=EMBEDDER, llm=None)
    assert scores[0].score == 0
    g, c = only_check(TC02_CV, 3)
    assert (g.status, c.basis, c.candidate_months, c.evidence) == ("PASS", "stated", 60, ("경력: 5년",))
    assert "근무 기간은 확인되지 않음" in c.reason


@pytest.mark.parametrize(
    "line, min_years, status",
    [
        # TC-13: 1 year against the DBA job's 3-year minimum
        ("경력: 1년", 3, "FAIL"),
        # The other 12 scenarios meet their job's minimum (TC-03 and TC-10: no minimum)
        ("경력: 2년", 1, "PASS"), ("경력: 5년", 3, "PASS"), ("경력: 5년", None, "PASS"), ("경력: 4년", 3, "PASS"),
        ("Số năm kinh nghiệm: 6", 5, "PASS"), ("Số năm kinh nghiệm: 3", 2, "PASS"), ("Số năm kinh nghiệm: 11", 10, "PASS"),
        ("Số năm kinh nghiệm: 4", None, "PASS"), ("Số năm kinh nghiệm: 4", 3, "PASS"), ("경력: 6년", 5, "PASS"),
    ],
)
def test_scenario_statuses(line, min_years, status):
    assert gate(f"자기소개\n백엔드 개발자\n{line}\n보유 기술\nJava", min_years).status == status


# ── no requirement ──


@pytest.mark.parametrize("min_years", [None, 0])
def test_no_minimum_passes_without_checks(min_years):
    g = gate("자기소개\nJava 개발", min_years)
    assert (g.status, g.checks, g.reason) == ("PASS", (), NO_REQUIREMENT_REASON)


def test_preferred_experience_never_triggers_the_gate():
    # A job without a minimum but with "3년 이상 우대" (3+ years preferred) as a criterion: the gate reads no criterion
    assert gate("경력: 0년\n자기소개\nPython 개발", None).status == "PASS"


# ── periods first ──


def test_sufficient_periods_pass():
    text = "경력\nAcme | 백엔드 개발자 2021.03 ~ 2025.02\n주문 API 개발"
    g, c = only_check(text, 3)
    assert (g.status, c.basis, c.candidate_months, c.evidence) == ("PASS", "periods", 48, ("Acme | 백엔드 개발자 2021.03 ~ 2025.02",))


def test_periods_take_priority_over_a_lower_stated_total():
    text = "경력: 1년\n경력\nAcme 개발자 2021.03 ~ 2025.02"
    g, c = only_check(text, 3)
    assert (g.status, c.basis, c.candidate_months) == ("PASS", "periods", 48)


def test_sample_cv_passes_on_its_periods():
    masked = mask_pii(SAMPLE_CV, ["김지원"]).text
    g, c = only_check(masked, 5)
    assert (g.status, c.basis, c.candidate_months) == ("PASS", "periods", 69)  # 2021.03 ~ 현재 (2026-11)


def test_short_periods_with_a_higher_stated_total_need_review():
    text = "경력: 10년\n경력\nAcme 개발자 2024.11 ~ 2026.10"
    g, c = only_check(text, 3)
    assert (g.status, c.basis, c.candidate_months) == ("REVIEW", "periods", 24)
    assert set(c.evidence) == {"Acme 개발자 2024.11 ~ 2026.10", "경력: 10년"} and "일치하지 않아" in c.reason


def test_short_periods_alone_need_review():
    # Periods may be only partly recognized (e.g. a range written with years only), so this is not FAIL
    text = "경력\nAcme 개발자 2025.01 ~ 2025.12\nBeta 개발자 2019 - 2023"
    g, c = only_check(text, 3)
    assert (g.status, c.basis, c.candidate_months) == ("REVIEW", "periods", 12)


def test_short_periods_and_a_low_stated_total_fail():
    text = "경력: 1년\n경력\nAcme 개발자 2025.01 ~ 2025.12"
    g, c = only_check(text, 3)
    assert (g.status, c.basis, c.candidate_months) == ("FAIL", "periods", 12)
    assert set(c.evidence) == {"Acme 개발자 2025.01 ~ 2025.12", "경력: 1년"}


# ── stated totals ──


@pytest.mark.parametrize(
    "line, min_years, status",
    [
        ("경력: 3년", 3, "PASS"),  # exactly the minimum
        ("경력: 2년 11개월", 3, "FAIL"),  # one month short
        ("경력: 6개월", 1, "FAIL"),
        ("5 years of experience in backend development", 3, "PASS"),
        ("Years of experience: 2", 3, "FAIL"),
        ("Kinh nghiệm: 4 năm", 3, "PASS"),
        # Ranges and open-ended statements
        ("경력: 2~4년", 3, "REVIEW"),  # crosses the minimum
        ("경력: 2~4년", 2, "PASS"),
        ("경력: 2~4년", 5, "FAIL"),  # even the upper bound is below
        ("3-5 years of experience", 4, "REVIEW"),
        ("경력: 2년 이상", 3, "REVIEW"),  # at least 2: may or may not reach 3
        ("Over 2 years of experience", 3, "REVIEW"),
        ("5+ years of experience", 3, "PASS"),
    ],
)
def test_stated_totals(line, min_years, status):
    g, c = only_check(f"자기소개\n{line}\n보유 기술\nJava", min_years)
    assert (g.status, c.basis, c.evidence) == (status, "stated", (line,))


def test_conflicting_stated_totals_need_review():
    g, c = only_check("경력: 2년\n자기소개\n총 경력 7년", 3)
    assert (g.status, c.candidate_months) == ("REVIEW", 24)
    assert c.evidence == ("경력: 2년", "총 경력 7년") and "서로 다른 경력" in c.reason


def test_stated_totals_that_agree_on_the_outcome_decide():
    assert gate("경력: 5년\n자기소개\n총 경력 7년", 3).status == "PASS"
    assert gate("경력: 1년\n자기소개\n총 경력 2년", 3).status == "FAIL"


def test_missing_experience_information_needs_review():
    g, c = only_check("자기소개\nJava 개발\n보유 기술\nJava", 3)
    assert (g.status, c.basis, c.candidate_months, c.evidence) == ("REVIEW", None, None, ())


def test_unreadable_statements_need_review():
    for line in ("경력: 2020년", "경력: 신입", "Experience: 5", "경력 3년 이상의 시니어와 협업"):
        assert gate(f"자기소개\n{line}", 3).status == "REVIEW", line


def test_the_edited_profile_alone_is_not_evidence():
    # Dates and a stated total only in the seeker-editable profile, not in the CV text
    exp = Experience(org="Acme", start="2010-01", end="2020-12", source="Acme 개발자 2010.01 ~ 2020.12")
    g, c = only_check("자기소개\nJava 개발", 3, [exp])
    assert (g.status, c.basis) == ("REVIEW", None)


def test_today_may_be_a_date():
    text = "경력\nAcme 개발자 2023.11 ~ 현재"
    assert required_gate(text, [], 3, date(2026, 11, 5)).status == required_gate(text, [], 3, "2026-11").status == "PASS"


# ── helper and unchanged behaviour ──


@pytest.mark.parametrize(
    "line, low, high",
    [
        ("경력: 2년", 24, 24), ("경력: 2~4년", 24, 48), ("경력: 2년~4년", 24, 48), ("경력: 1년 6개월", 18, 18),
        ("경력: 6~8개월", 6, 8), ("경력: 3년 이상", 36, None), ("5+ years of experience", 60, None),
        ("Over 5 years of experience", 60, None), ("3-5 years of experience", 36, 60), ("Số năm kinh nghiệm: 0", 0, 0),
    ],
)
def test_stated_experience_candidates(line, low, high):
    assert stated_experience_candidates(f"자기소개\n{line}") == [StatedExperience(low, high, line)]


def test_stated_experience_is_unchanged():
    # The scorer's helper keeps its return values: the smallest lower bound and its line (D48)
    assert stated_experience("경력: 7년\n자기소개\n총 경력 2년") == (24, "총 경력 2년")
    assert stated_experience("경력: 2~4년") == (24, "경력: 2~4년")
    assert stated_experience("자기소개\nJava") is None


def test_the_gate_leaves_scores_fit_and_inputs_unchanged():
    masked = mask_pii(SAMPLE_CV, ["김지원"]).text
    profile = CvProfile(experiences=[Experience(org="(주)넥스트코드", start="2021-03", end="2023-02",
                                                source="(주)넥스트코드 | 백엔드 개발자 2021.03 ~ 2023.02")])
    cand = Candidate(profile, masked)
    criteria = [Criterion(1, "Java 활용 능력", "", "skill", 60), Criterion(2, "경력 3년 이상", "", "experience", 40)]
    job = JobContext(title="백엔드 개발자", min_experience_years=3)

    def fit():
        results = score_candidate(criteria, cand, job, skills=SKILLS, embedder=EMBEDDER, llm=None, today=date(2026, 10, 1))
        return results, aggregate_fit({r.criterion_id: r.score for r in results}, {c.id: c.weight for c in criteria})

    before = fit()
    snapshot = dataclasses.replace(cand)
    required_gate(cand.text, cand.profile.experiences, job.min_experience_years, "2026-10")
    assert fit() == before and before[1] == 88.0  # Java 80 · 0.6 + experience 100 · 0.4
    assert cand == snapshot and verified_experience(masked, profile.experiences, "2026-10")[0] == 68
