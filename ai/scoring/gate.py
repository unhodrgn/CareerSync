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
NO_REQUIREMENT_REASON = "필수 경력 조건 없음"


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
    if not years:
        return f"{rest}개월"
    return f"{years}년 {rest}개월" if rest else f"{years}년"


def _stated_text(s: StatedExperience) -> str:
    if s.high_months is None:
        return f"{_span(s.low_months)} 이상"
    if s.high_months != s.low_months:
        return f"{_span(s.low_months)}~{_span(s.high_months)}"
    return _span(s.low_months) if s.low_months else "0년"


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
    need = f"최소 경력 {min_years}년"
    months, period_lines = verified_experience(text, experiences, today)
    stated = stated_experience_candidates(text)
    stated_lines = [s.line for s in stated]

    if period_lines:
        if months >= required:
            # Employment periods take priority (D48); a lower stated total does not block them
            return _check("PASS", required, months, "periods", f"근무 기간 기준 경력 약 {_span(months)} ({need})", period_lines)
        if stated and all(_relation(s, required) == "below" for s in stated):
            stated_part = ", ".join(_stated_text(s) for s in stated)
            reason = f"근무 기간 약 {_span(months)}, 이력서 기재 경력 {stated_part}: {need}에 미달"
            return _check("FAIL", required, months, "periods", reason, [*period_lines, *stated_lines])
        if stated:
            stated_part = ", ".join(_stated_text(s) for s in stated)
            reason = f"근무 기간(약 {_span(months)})과 이력서 기재 경력({stated_part})이 일치하지 않아 확인 필요"
            return _check("REVIEW", required, months, "periods", reason, [*period_lines, *stated_lines])
        # Periods alone below the minimum: some periods may not be recognized (e.g. years without months)
        reason = f"근무 기간 기준 경력 약 {_span(months)}: {need}에 미달하나 인식되지 않은 기간이 있을 수 있어 확인 필요"
        return _check("REVIEW", required, months, "periods", reason, period_lines)

    if not stated:
        return _check("REVIEW", required, None, None, "이력서에서 경력 정보를 확인할 수 없어 확인 필요", [])
    relations = {_relation(s, required) for s in stated}
    lowest = min(s.low_months for s in stated)
    stated_part = ", ".join(_stated_text(s) for s in stated)
    if relations == {"met"}:
        reason = f"이력서 기재 경력 {stated_part} ({need}), 근무 기간은 확인되지 않음"
        return _check("PASS", required, lowest, "stated", reason, stated_lines)
    if relations == {"below"}:
        highest = max(s.high_months for s in stated)  # every one is bounded when all are below
        return _check("FAIL", required, highest, "stated", f"이력서 기재 경력 {stated_part}: {need}에 미달", stated_lines)
    if len(stated) > 1 and "crossing" not in relations:
        reason = f"이력서에 서로 다른 경력({stated_part})이 기재되어 확인 필요"
    else:
        reason = f"이력서 기재 경력({stated_part})만으로는 {need} 충족 여부를 판단할 수 없어 확인 필요"
    return _check("REVIEW", required, lowest, "stated", reason, stated_lines)


def required_gate(text: str, experiences: list[Experience], min_years: int | None, today: date | str) -> RequiredGate:
    """Gate status of one CV (masked text + its profile's experiences, used only as `verified_experience` uses them)
    against one job's `min_experience_years`. `today` is a date or "YYYY-MM" (for periods ending 현재/present)."""
    if not min_years:
        return RequiredGate("PASS", (), NO_REQUIREMENT_REASON)
    month = today.strftime("%Y-%m") if isinstance(today, date) else today
    check = min_experience_check(text, experiences, min_years, month)
    return RequiredGate(check.status, (check,))
