from ai.parsing.universal_jd import analyze_universal_jd
from ai.tests.helpers import FakeLLM


def req(rid, text, source):
    return dict(requirement_id=rid, role="회계 담당", kind="required", category="세무회계",
                text=text, source=source, logic="single")


def test_non_it_requirements_preserve_alternatives():
    jd = "전산세무 2급 또는 관련 결산 경험 필수"
    r = req("R1", jd, jd)
    r.update(logic="any", alternatives=["전산세무 2급", "관련 결산 경험"])
    llm = FakeLLM({"profile": {}, "requirements": [r], "criteria": [
        {"name": "세무회계 역량", "category": "other", "weight": 25, "requirement_ids": ["R1"]}
    ]})
    out = analyze_universal_jd("회계 담당", jd, None, llm)
    assert out.requirements[0].logic == "any"
    assert out.criteria[0].weight == 100
    assert not out.warnings


def test_invalid_source_and_dangling_links():
    llm = FakeLLM({"profile": {}, "requirements": [
        req("R1", "결산 경험", "결산 경험"), req("R2", "Python", "Python")
    ], "criteria": [
        {"name": "결산", "category": "other", "weight": 20, "requirement_ids": ["R1"]},
        {"name": "Python", "category": "skill", "weight": 80, "requirement_ids": ["R2"]}
    ]})
    out = analyze_universal_jd("회계 담당", "결산 경험", None, llm)
    assert [r.requirement_id for r in out.requirements] == ["R1"]
    assert [c.name for c in out.criteria] == ["결산"]
    assert out.criteria[0].weight == 100
    assert out.warnings


def test_requirements_not_limited_to_ten():
    texts = [f"업무 역량 {i}" for i in range(15)]
    llm = FakeLLM({"profile": {}, "requirements": [
        req(f"R{i}", t, t) for i, t in enumerate(texts)
    ], "criteria": [
        {"name": "업무 수행", "category": "other", "weight": 100,
         "requirement_ids": [f"R{i}" for i in range(15)]}
    ]})
    out = analyze_universal_jd("회계 담당", "\n".join(texts), None, llm)
    assert len(out.requirements) == 15
    assert len(out.criteria) == 1
