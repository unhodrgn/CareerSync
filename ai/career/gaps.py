"""Skills and certificates a job asks for that the CV text does not show (docs/DECISIONS.md D21, Q3 option C).

Computed in code from public job information (criteria names and descriptions, the JD) and the masked CV
text, never from the company's scores, so seekers learn nothing about how they were evaluated (D1).
Only skills and certificates in data/skills.yaml are recognized.
"""
from dataclasses import dataclass
from typing import Literal

from ai.embedding.skills import SkillDictionary


@dataclass(frozen=True)
class Gap:
    name: str  # canonical name from data/skills.yaml
    kind: Literal["skill", "certificate"]


def find_gaps(criteria_texts: list[str], job_text: str, cv_text: str, skills: SkillDictionary) -> list[Gap]:
    """In order of appearance, criteria first (they are what the company evaluates on), then the JD."""
    wanted_text = "\n".join([*criteria_texts, job_text])
    have_skills = set(skills.find_in_text(cv_text))
    have_certs = {name for name, _ in skills.find_certificates(cv_text)}
    gaps = [Gap(name, "skill") for name in skills.find_in_text(wanted_text) if name not in have_skills]
    certs = dict.fromkeys(name for name, _ in skills.find_certificates(wanted_text))
    gaps += [Gap(name, "certificate") for name in certs if name not in have_certs]
    return gaps
