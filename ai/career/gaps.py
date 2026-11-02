"""Skills and certificates a job asks for that the CV text does not show (docs/DECISIONS.md D21, Q3 option C),
and those it does show (strengths in job recommendation, D43).

Computed in code from public job information (criteria names and descriptions, the JD) and the masked CV
text, never from the company's scores, so seekers learn nothing about how they were evaluated (D42).
Only skills and certificates in data/skills.yaml are recognized.
"""
from dataclasses import dataclass
from typing import Literal

from ai.embedding.skills import SkillDictionary


@dataclass(frozen=True)
class Gap:
    name: str  # canonical name from data/skills.yaml
    kind: Literal["skill", "certificate"]


def match_skills(criteria_texts: list[str], job_text: str, cv_text: str, skills: SkillDictionary) -> tuple[list[Gap], list[Gap]]:
    """(strengths, gaps): the skills and certificates the job names that the CV text shows, and those it lacks.
    In order of appearance, criteria first (they are what the company evaluates on), then the JD."""
    wanted_text = "\n".join([*criteria_texts, job_text])
    have_skills = set(skills.find_in_text(cv_text))
    have_certs = {name for name, _ in skills.find_certificates(cv_text)}
    wanted_skills = [Gap(name, "skill") for name in skills.find_in_text(wanted_text)]
    wanted_certs = [Gap(name, "certificate") for name in dict.fromkeys(name for name, _ in skills.find_certificates(wanted_text))]
    strengths = [g for g in wanted_skills if g.name in have_skills] + [g for g in wanted_certs if g.name in have_certs]
    gaps = [g for g in wanted_skills if g.name not in have_skills] + [g for g in wanted_certs if g.name not in have_certs]
    return strengths, gaps


def find_gaps(criteria_texts: list[str], job_text: str, cv_text: str, skills: SkillDictionary) -> list[Gap]:
    """The gaps of `match_skills`."""
    return match_skills(criteria_texts, job_text, cv_text, skills)[1]
