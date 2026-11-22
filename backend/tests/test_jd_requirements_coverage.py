"""LIKEY front-end JD regression: alternatives, required/preferred, coverage."""
from ai.embedding.skills import SkillDictionary
from ai.parsing.extract import analyze_jd_rules
from ai.parsing.jd_requirements import criteria_from_requirements, extract_requirements

LIKEY = """담당업무
- 라이키의 웹 화면과 기능 개발
- 모호한 요구사항은 기획자와 확인해 스펙에 반영
자격요건
- Vue 또는 React와 TypeScript로 웹 기능을 구현한 경험이 있는 분
- API 연동, 비동기 처리, 상태 관리를 이해하는 분
- AI 코딩 도구를 활용해 실제 문제를 해결한 경험이 있는 분
- 요구사항의 모호한 부분을 발견하고 질문·가정·결정 사항을 구분할 수 있는 분
- 정상 동작과 실패 상황을 확인하고 발견한 문제를 수정할 수 있는 분
우대사항
- Vue/Nuxt, 모바일 웹, Vue 2에서 Vue 3로의 전환 경험
- 테스트 자동화, 코드 리뷰, 개발 도구 개선 경험
- 기획자·디자이너 등 다른 직군과 협업한 경험
"""


def test_extract_preserves_or_and_section_kind():
    reqs = extract_requirements(LIKEY)
    assert any(r.kind == "required" and set(r.alternatives) == {"Vue", "React"} for r in reqs)
    assert any(r.kind == "preferred" and "Nuxt" in r.source for r in reqs)
    assert any("AI 코딩" in r.source for r in reqs)


def test_fallback_keeps_more_than_three_keywords():
    skills = SkillDictionary(version="test", skills={}, certificates={}, alias_to_skill={})
    result = analyze_jd_rules("웹 프론트엔드 개발자", LIKEY, None, skills)
    items = result.criteria
    assert 5 <= len(items) <= 10
    assert sum(c.weight for c in items) == 100
    assert any("Vue/React" in c.name and "또는" in c.description for c in items)
    assert any("AI 코딩" in c.name for c in items)
    assert any("API" in c.name for c in items)
    assert all(c.source and c.reason for c in items)
    assert len(set(c.name for c in items)) == len(items)


def test_no_bullets_does_not_invent_requirements():
    assert extract_requirements("채용공고\nJava 개발") == []
    assert criteria_from_requirements([]) == []
