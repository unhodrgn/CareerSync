"""Pref: mean over the preference fields the seeker filled in (D15)."""
import pytest

from ai.scoring.pref import JobFacts, Preferences, keyword_matches, location_matches, pref_score

JOB = JobFacts(
    title="백엔드 개발자",
    description="Java, Spring Boot 기반 API 개발. JavaScript 경험 우대.",
    location="서울 강남구",
    employment_type="full_time",
)


def test_nothing_filled_in_is_100():
    r = pref_score(Preferences(), JOB)
    assert (r.score, r.matched, r.missed) == (100.0, (), ())


def test_only_filled_fields_count():
    assert pref_score(Preferences(locations=("부산",)), JOB).score == 0  # one field, no match
    two = pref_score(Preferences(locations=("부산",), employment_types=("full_time",)), JOB)
    assert (two.score, two.matched, two.missed) == (50.0, ("employment_types",), ("locations",))
    all_three = Preferences(locations=("서울",), employment_types=("contract",), job_keywords=("백엔드",))
    r = pref_score(all_three, JOB)
    assert r.score == 66.7 and r.missed == ("employment_types",)
    full = Preferences(locations=("서울",), employment_types=("full_time", "contract"), job_keywords=("Spring",))
    assert pref_score(full, JOB).score == 100.0


@pytest.mark.parametrize(
    "wanted, job_location, expected",
    [
        ("서울", "서울 강남구", True),
        ("서울 강남구", "서울", True),
        ("  서울   강남구 ", "서울 강남구", True),
        ("Seoul", "seoul", True),
        ("부산", "서울 강남구", False),
        ("서울", "", False),
    ],
)
def test_location_matching(wanted, job_location, expected):
    assert location_matches(wanted, job_location) is expected


@pytest.mark.parametrize(
    "keyword, text, expected",
    [
        ("백엔드", "백엔드 개발자", True),
        ("백엔드", "웹 백엔드개발", True),  # Korean: plain substring
        ("java", "Java, Spring 기반", True),
        ("Java", "JavaScript 개발자", False),  # Latin: whole word
        ("Script", "JavaScript 개발자", False),
        ("Spring Boot", "Spring  Boot 기반", True),
        ("Node.js", "Node.js 서버", True),
        ("C++", "C++ 개발", True),
        ("API", "API를 설계", True),  # Hangul right after is still a boundary
        ("프론트", "백엔드 개발자", False),
    ],
)
def test_keyword_matching(keyword, text, expected):
    assert keyword_matches(keyword, text) is expected


def test_keyword_found_in_the_jd_only():
    assert pref_score(Preferences(job_keywords=("Spring",)), JOB).score == 100.0
    assert pref_score(Preferences(job_keywords=("Java",)), JobFacts(title="프론트엔드", description="JavaScript, React")).score == 0
