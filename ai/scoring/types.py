"""Inputs and outputs of the scorer, independent of the DB and the web layer."""
from dataclasses import dataclass, field

from ai.parsing.profile import CvProfile

LEVELS = (0, 25, 50, 75, 100)


@dataclass(frozen=True)
class Criterion:
    id: int
    name: str
    description: str
    category: str  # skill | experience | project | certificate | education | other
    # Effective weight; a criteria set sums to 100
    weight: float


@dataclass(frozen=True)
class JobContext:
    title: str
    description: str = ""
    min_experience_years: int | None = None
    company_name: str = ""
    # 인재상
    talent_profile: str = ""


@dataclass(frozen=True)
class Candidate:
    profile: CvProfile
    # PII-masked CV text: retrieval reads it and every evidence quote must appear in it
    text: str


@dataclass(frozen=True)
class CriterionResult:
    criterion_id: int
    score: int  # 0-100
    level: int  # nearest of LEVELS
    reason: str  # one Korean sentence
    evidence: tuple[str, ...] = field(default_factory=tuple)
    # How the score was produced, e.g. "rule:skill", "llm:claude-sonnet-5-5", "retrieval"
    method: str = ""


def nearest_level(score: float) -> int:
    return min(LEVELS, key=lambda lv: (abs(lv - score), -lv))
