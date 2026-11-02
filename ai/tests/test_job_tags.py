"""Job tags (docs/DECISIONS.md D45): skills from the criteria and the JD, criteria first, capped; search by alias."""
from ai.embedding.skills import load_dictionary
from ai.jd.tags import job_tags, matches_tag

SKILLS = load_dictionary()


def test_tags_come_from_criteria_first_then_the_jd_without_duplicates():
    criteria = ["Spring 경험: Spring Boot 실무", "DB 경험: PostgreSQL 튜닝"]
    tags = job_tags(criteria, "백엔드 개발자\nJava와 Spring으로 API를 만듭니다. Docker 사용", SKILLS, limit=10)
    assert tags[:2] == ["Spring", "PostgreSQL"]
    assert "Java" in tags and "Docker" in tags
    assert len(tags) == len(set(tags))


def test_tags_are_capped_and_only_known_skills():
    assert job_tags([], "Java Python Go Rust Swift Kotlin", SKILLS, limit=3) == ["Java", "Python", "Go"]
    assert job_tags(["커뮤니케이션 능력"], "성실하고 꼼꼼한 분", SKILLS, limit=5) == []


def test_search_matches_part_of_a_tag_or_an_alias():
    tags = ["React", "TypeScript"]
    assert matches_tag("react", tags, SKILLS)
    assert matches_tag("Script", tags, SKILLS)
    assert matches_tag("리액트", tags, SKILLS)
    assert not matches_tag("Java", tags, SKILLS)
    assert not matches_tag("  ", tags, SKILLS)
