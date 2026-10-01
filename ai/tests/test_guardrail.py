from pathlib import Path

import pytest
import yaml

from ai.guardrails.blocklist import BlocklistError, load_blocklist, parse_blocklist
from ai.guardrails.criteria import check_criterion

ROOT = Path(__file__).resolve().parents[2]
BLOCKLIST = load_blocklist(ROOT / "data" / "blocklist.yaml")
CASES = yaml.safe_load((Path(__file__).parent / "fixtures" / "guardrail_cases.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("phrase", "rule_id"), CASES["block"])
def test_blocks(phrase, rule_id):
    result = check_criterion(phrase, "", BLOCKLIST)
    assert not result.allowed
    assert rule_id in {h.rule_id for h in result.hits}


@pytest.mark.parametrize("phrase", CASES["allow"])
def test_allows(phrase):
    result = check_criterion(phrase, "", BLOCKLIST)
    assert result.allowed, [(h.rule_id, h.matched) for h in result.hits]


def test_description_is_checked_too():
    result = check_criterion("기본 소양", "용모가 단정하고 키 175 이상인 분", BLOCKLIST)
    assert {(h.field, h.rule_id) for h in result.hits} == {
        ("description", "physical.appearance"),
        ("description", "physical.height"),
    }


def test_hit_carries_reason_and_law():
    hit = check_criterion("미혼자 우대", "", BLOCKLIST).hits[0]
    assert hit.law_ref == "채용절차법 제4조의3 제2호"
    assert hit.reason and hit.matched == "미혼"


def test_deterministic():
    results = {check_criterion("남성 우대, 30세 이하", "", BLOCKLIST) for _ in range(3)}
    assert len(results) == 1


def test_bad_regex_fails_at_load():
    with pytest.raises(BlocklistError):
        parse_blocklist({"version": "x", "rules": [{"id": "a", "category": "c", "law_ref": "l", "reason": "r", "patterns": ["("]}]})


def test_duplicate_rule_id_fails_at_load():
    rule = {"id": "a", "category": "c", "law_ref": "l", "reason": "r", "patterns": ["x"]}
    with pytest.raises(BlocklistError):
        parse_blocklist({"version": "x", "rules": [rule, rule]})
