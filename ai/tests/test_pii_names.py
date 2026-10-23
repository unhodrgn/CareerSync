"""Best-effort masking of person names (docs/DECISIONS.md D39): the account name in its spellings, labeled name lines
(also 추천인/담당자/Reference), and a name at the top of the CV, each then masked wherever it appears.

Cases live in fixtures/pii_name_cases.yaml (synthetic names only): `masked` strings must not survive (case and
diacritics ignored), `kept` strings must survive exactly. `known_leaks` are out of scope and only counted."""
import pytest
import yaml

from ai.parsing.pii import _fold, mask_pii
from ai.parsing.sections import split_sections
from ai.tests.helpers import FIXTURES, SKILLS

CASES = yaml.safe_load((FIXTURES / "pii_name_cases.yaml").read_text(encoding="utf-8"))["cases"]
IDS = [c["id"] for c in CASES]


def _masked(case) -> str:
    return mask_pii(case["text"], case.get("names") or [], SKILLS).text


def leaks(case, text: str) -> list[str]:
    return [s for s in case.get("masked") or [] if _fold(s) in _fold(text)]


def false_positives(case, text: str) -> list[str]:
    return [s for s in case.get("kept") or [] if s not in text]


def known_leaks(case, text: str) -> list[str]:
    return [s for s in case.get("known_leaks") or [] if _fold(s) in _fold(text)]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_names_are_masked_and_everything_else_is_kept(case):
    text = _masked(case)
    assert leaks(case, text) == []
    assert false_positives(case, text) == []


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_masking_is_idempotent_and_keeps_every_section(case):
    once = _masked(case)
    assert mask_pii(once, case.get("names") or [], SKILLS).text == once
    assert [s.key for s in split_sections(once)] == [s.key for s in split_sections(case["text"])]


def test_every_in_scope_case_has_no_leak_and_no_false_positive():
    texts = {c["id"]: _masked(c) for c in CASES}
    assert sum(len(leaks(c, texts[c["id"]])) for c in CASES) == 0
    assert sum(len(false_positives(c, texts[c["id"]])) for c in CASES) == 0


def test_a_found_name_counts_as_masked_data():
    assert "name" in mask_pii("윤서아\n\n경력\n- 주문 API 개발", [], SKILLS).masked
    assert "name" not in mask_pii("이력서\n\n경력\n- 주문 API 개발", [], SKILLS).masked


def test_without_the_skill_dictionary_a_skill_line_at_the_top_can_be_taken_for_a_name():
    """Why cv_service passes the dictionary: "Java Spring" is name-shaped."""
    text = "Java Spring\n\n경력\n- Java 개발"
    assert "Java Spring" in mask_pii(text, [], SKILLS).text
    assert "Java Spring" not in mask_pii(text, []).text
