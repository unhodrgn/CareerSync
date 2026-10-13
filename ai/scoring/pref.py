"""Pref: how well a job matches the seeker's stated preferences (docs/DECISIONS.md D15).

Three fields, each 0 or 100: desired locations, employment types, role keywords. Pref is the mean
over the fields the seeker filled in; a field left empty is not counted. Nothing filled in → 100.
Rule-based only (no LLM, no embeddings); synonyms are not handled (PROJECT_DOCUMENTATION.md Q1).
"""
import re
from dataclasses import dataclass

LOCATIONS, EMPLOYMENT_TYPES, JOB_KEYWORDS = "locations", "employment_types", "job_keywords"


@dataclass(frozen=True)
class Preferences:
    locations: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    job_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class JobFacts:
    title: str
    description: str = ""
    location: str = ""
    employment_type: str = ""


@dataclass(frozen=True)
class PrefResult:
    score: float  # 0-100, one decimal
    matched: tuple[str, ...]  # field names that match
    missed: tuple[str, ...]  # field names filled in that do not match


def normalize(text: str) -> str:
    """Case-insensitive, whitespace collapsed."""
    return " ".join(text.split()).casefold()


def location_matches(wanted: str, job_location: str) -> bool:
    """Equal, or one contains the other ("서울" matches "서울 강남구" and the reverse)."""
    a, b = normalize(wanted), normalize(job_location)
    return bool(a and b) and (a in b or b in a)


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def keyword_matches(keyword: str, text: str) -> bool:
    """Substring match; a keyword that starts or ends with a Latin letter or digit must start or end
    on a word boundary there, so "Java" does not match "JavaScript"."""
    kw = normalize(keyword)
    if not kw:
        return False
    before = r"(?<![a-z0-9])" if _is_latin(kw[0]) else ""
    after = r"(?![a-z0-9])" if _is_latin(kw[-1]) else ""
    return re.search(before + re.escape(kw) + after, normalize(text)) is not None


def pref_score(prefs: Preferences, job: JobFacts) -> PrefResult:
    checks: dict[str, bool] = {}
    if prefs.locations:
        checks[LOCATIONS] = any(location_matches(loc, job.location) for loc in prefs.locations)
    if prefs.employment_types:
        checks[EMPLOYMENT_TYPES] = job.employment_type in prefs.employment_types
    if prefs.job_keywords:
        text = f"{job.title}\n{job.description}"
        checks[JOB_KEYWORDS] = any(keyword_matches(kw, text) for kw in prefs.job_keywords)
    if not checks:
        return PrefResult(100.0, (), ())
    matched = tuple(name for name, ok in checks.items() if ok)
    missed = tuple(name for name, ok in checks.items() if not ok)
    return PrefResult(round(100 * len(matched) / len(checks), 1), matched, missed)
