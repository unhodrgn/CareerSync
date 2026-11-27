"""Required criteria gate (docs/DECISIONS.md D50), MVP: the job's minimum experience.

A status next to Fit, never part of it: PASS when every reliably verifiable hard requirement is met, FAIL when the CV
text explicitly shows one is not met, REVIEW when the information is missing, conflicting or ambiguous. The only hard
requirement in the MVP is `job_postings.min_experience_years` (NULL or 0 = no requirement); criteria, their scores and
preferred items are never read, so a criterion scored 0 cannot cause FAIL.

Experience comes from the masked CV text only, never from the editable profile (CLAUDE.md AI rule 14): employment
periods first (`verified_experience`), the stated total (`stated_experience_candidates`, D48) only when the text has no
period. Ambiguity can block PASS but never produces FAIL. Pure, rules only: no LLM, no database.

The gate is a recommendation filter, not a hiring decision: it never changes an application (AI rule 5).
"""
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ai.parsing.extract import StatedExperience, stated_experience_candidates, verified_experience
from ai.parsing.profile import Experience

GateStatus = Literal["PASS", "FAIL", "REVIEW"]
MIN_EXPERIENCE = "min_experience"
MIN_EXPERIENCE_SOURCE = "job.min_experience_years"
NO_REQUIREMENT_REASON = "No minimum experience requirement"


@dataclass(frozen=True)
class RequirementCheck:
    kind: str  # "min_experience"
    source: str  # where the requirement comes from: "job.min_experience_years"
    required_months: int
    candidate_months: int | None  # the experience the decision used; None when the CV gives none
    basis: Literal["periods", "stated"] | None  # periods = verified_experience, stated = the CV's stated total
    status: GateStatus
    reason: str  # one Korean sentence
    evidence: tuple[str, ...] = ()  # CV lines: period lines or stated lines


@dataclass(frozen=True)
class RequiredGate:
    status: GateStatus
    checks: tuple[RequirementCheck, ...] = ()
    # Shown when there is no check (e.g. no minimum set)
    reason: str = ""


def _span(months: int) -> str:
    years, rest = divmod(months, 12)
    y_str = f"{years} year{'s' if years != 1 else ''}"
    m_str = f"{rest} month{'s' if rest != 1 else ''}"
    if not years:
        return m_str
    return f"{y_str} {m_str}" if rest else y_str


def _stated_text(s: StatedExperience) -> str:
    if s.high_months is None:
        return f"{_span(s.low_months)}+"
    if s.high_months != s.low_months:
        return f"{_span(s.low_months)}–{_span(s.high_months)}"
    return _span(s.low_months) if s.low_months else "0 years"


def _relation(s: StatedExperience, required: int) -> Literal["met", "below", "crossing"]:
    """met: the statement's lower bound reaches the minimum; below: even its upper bound does not; else crossing."""
    if s.low_months >= required:
        return "met"
    if s.high_months is not None and s.high_months < required:
        return "below"
    return "crossing"


def _check(status: GateStatus, required: int, months: int | None, basis, reason: str, evidence) -> RequirementCheck:
    return RequirementCheck(
        MIN_EXPERIENCE, MIN_EXPERIENCE_SOURCE, required, months, basis, status, reason, tuple(dict.fromkeys(evidence))
    )


def min_experience_check(text: str, experiences: list[Experience], min_years: int, today: str) -> RequirementCheck:
    required = 12 * min_years
    need = f"minimum {min_years} year{'s' if min_years != 1 else ''} of experience"
    months, period_lines = verified_experience(text, experiences, today)
    stated = stated_experience_candidates(text)
    stated_lines = [s.line for s in stated]

    if period_lines:
        if months >= required:
            # Employment periods take priority (D48); a lower stated total does not block them
            return _check("PASS", required, months, "periods", f"About {_span(months)} from employment periods ({need})", period_lines)
        if stated and all(_relation(s, required) == "below" for s in stated):
            stated_part = ", ".join(_stated_text(s) for s in stated)
            reason = f"Employment periods ~{_span(months)}, stated experience {stated_part}: below {need}"
            return _check("FAIL", required, months, "periods", reason, [*period_lines, *stated_lines])
        if stated:
            stated_part = ", ".join(_stated_text(s) for s in stated)
            reason = f"Employment periods (~{_span(months)}) do not match stated experience ({stated_part}); review needed"
            return _check("REVIEW", required, months, "periods", reason, [*period_lines, *stated_lines])
        # Periods alone below the minimum: some periods may not be recognized (e.g. years without months)
        reason = f"About {_span(months)} from employment periods: below {need}, though unrecognized periods may exist; review needed"
        return _check("REVIEW", required, months, "periods", reason, period_lines)

    if not stated:
        return _check("REVIEW", required, None, None, "No experience information could be verified in the CV; review needed", [])
    relations = {_relation(s, required) for s in stated}
    lowest = min(s.low_months for s in stated)
    stated_part = ", ".join(_stated_text(s) for s in stated)
    if relations == {"met"}:
        reason = f"Stated experience {stated_part} ({need}); employment periods could not be verified"
        return _check("PASS", required, lowest, "stated", reason, stated_lines)
    if relations == {"below"}:
        highest = max(s.high_months for s in stated)  # every one is bounded when all are below
        return _check("FAIL", required, highest, "stated", f"Stated experience {stated_part}: below {need}", stated_lines)
    if len(stated) > 1 and "crossing" not in relations:
        reason = f"Conflicting stated experience totals ({stated_part}); review needed"
    else:
        reason = f"Stated experience ({stated_part}) alone cannot confirm {need}; review needed"
    return _check("REVIEW", required, lowest, "stated", reason, stated_lines)


def required_gate(text: str, experiences: list[Experience], min_years: int | None, today: date | str) -> RequiredGate:
    """Gate status of one CV (masked text + its profile's experiences, used only as `verified_experience` uses them)
    against one job's `min_experience_years`. `today` is a date or "YYYY-MM" (for periods ending 현재/present)."""
    if not min_years:
        return RequiredGate("PASS", (), NO_REQUIREMENT_REASON)
    month = today.strftime("%Y-%m") if isinstance(today, date) else today
    check = min_experience_check(text, experiences, min_years, month)
    return RequiredGate(check.status, (check,))
