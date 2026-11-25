"""Occupation-independent LLM extraction. Quote checks establish provenance, not semantic correctness."""
import json
import unicodedata
from pathlib import Path

from ai.llm.client import LLMClient
from ai.parsing.extract import fix_weights
from ai.parsing.profile import JdAnalysis, JdRequirement

SCHEMA_VERSION = "jd_requirements.v1"
PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "v1" / "jd_universal.md"


class UniversalOutput(JdAnalysis):
    requirements: list[JdRequirement]


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def analyze_universal_jd(title: str, text: str, min_years: int | None, llm: LLMClient) -> JdAnalysis:
    result = llm.complete_json(
        PROMPT.read_text(encoding="utf-8"),
        json.dumps({"target_title": title, "document": text}, ensure_ascii=False),
        UniversalOutput, max_tokens=16000,
    )
    source = _normalize(text)
    warnings = []
    requirements = []
    counts: dict[str, int] = {}
    for r in result.requirements:
        counts[r.requirement_id] = counts.get(r.requirement_id, 0) + 1
    for r in result.requirements:
        quote = _normalize(r.source)
        if counts[r.requirement_id] != 1 or not r.requirement_id.strip():
            warnings.append(f"Duplicate or empty requirement ID: {r.requirement_id}")
        elif not quote or quote not in source:
            warnings.append(f"Unverified source: {r.requirement_id}")
        elif not all(v.strip() for v in (r.text, r.role, r.category)):
            warnings.append(f"Empty fields: {r.requirement_id}")
        else:
            requirements.append(r)
    ids = {r.requirement_id for r in requirements}
    criteria = []
    names = set()
    for c in result.criteria:
        name = _normalize(c.name).casefold()
        links = c.requirement_ids
        if not name or name in names or not links or not set(links) <= ids or len(links) != len(set(links)):
            warnings.append(f"Invalid criterion links or name: {c.name}")
            continue
        names.add(name)
        criteria.append(c)
    criteria = fix_weights(criteria)
    covered = {rid for c in criteria for rid in c.requirement_ids}
    if ids - covered:
        warnings.append("Requirements not mapped to criteria: " + ", ".join(sorted(ids - covered)))
    if not requirements:
        warnings.append("No source-backed requirements found; review the original document.")
    if min_years is not None:
        result.profile.min_years = min_years
    return JdAnalysis(profile=result.profile, criteria=criteria, requirements=requirements,
                      requirement_schema=SCHEMA_VERSION, warnings=warnings)
