"""Job tags for the public job list and search (docs/DECISIONS.md D45).

Computed in code from public job information only (criteria names and descriptions, the title and the JD), with
the same dictionary as the skill gaps (D21): only skills in data/skills.yaml are recognized. Tags are for display
and search; scoring never reads them.
"""
from ai.embedding.skills import SkillDictionary


def job_tags(criteria_texts: list[str], job_text: str, skills: SkillDictionary, limit: int) -> list[str]:
    """Canonical skill names, criteria first (what the company evaluates on), then the JD; at most `limit`."""
    out: list[str] = []
    for text in [*criteria_texts, job_text]:
        for name in skills.find_in_text(text):
            if name not in out:
                out.append(name)
    return out[:limit]


def matches_tag(query: str, tags: list[str], skills: SkillDictionary) -> bool:
    """True when the search text is part of a tag, or is an alias of one (e.g. "리액트" for React)."""
    q = query.strip().casefold()
    if not q:
        return False
    return any(q in tag.casefold() for tag in tags) or skills.canonical(query.strip()) in tags
