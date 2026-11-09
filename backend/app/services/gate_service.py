"""Required criteria gate for one (job, CV version) (docs/DECISIONS.md D50), shared by job recommendation, talent,
offers, the applicant list, the evaluation detail and job detail, so they can never disagree.

Inputs: the CV version's masked text, its profile experiences (only as `verified_experience` uses them: a line counts
when it is in the text) and `job_postings.min_experience_years`. The rules are in `ai.scoring.gate`; this module only
reads the rows, memoizes within one request and shapes the response. Computed when read, never stored.
"""
from datetime import date

from ai.parsing.profile import CvProfile as ProfileData
from ai.scoring.gate import RequiredGate, required_gate
from app.models import CvProfile
from app.schemas.gate import RequiredGateBrief, RequiredGateOut, RequirementCheckOut
from app.services import cv_service


def compute(profile: CvProfile, min_years: int | None, data: ProfileData | None = None, today: str | None = None) -> RequiredGate:
    """The gate of one CV version against one job's minimum. Pass `data` when the caller already has
    `cv_service.to_profile_data(profile)`."""
    data = data if data is not None else cv_service.to_profile_data(profile)
    return required_gate(profile.document.masked_text, data.experiences, min_years, today or date.today().strftime("%Y-%m"))


class Gates:
    """Memo for one request: the profile data is read once per CV version and the gate once per (CV version,
    minimum), however many jobs or candidates the request goes through."""

    def __init__(self, today: str | None = None):
        self.today = today or date.today().strftime("%Y-%m")
        self._data: dict[int, ProfileData] = {}
        self._gates: dict[tuple[int, int | None], RequiredGate] = {}

    def get(self, profile: CvProfile, min_years: int | None) -> RequiredGate:
        key = (profile.id, min_years or None)
        if key not in self._gates:
            if profile.id not in self._data:
                self._data[profile.id] = cv_service.to_profile_data(profile)
            self._gates[key] = compute(profile, min_years, self._data[profile.id], self.today)
        return self._gates[key]


def excluded(gate: RequiredGate) -> bool:
    """Automated recommendation paths (job recommendation, talent, offers) leave out FAIL; REVIEW stays (D50)."""
    return gate.status == "FAIL"


def to_out(gate: RequiredGate) -> RequiredGateOut:
    checks = [
        RequirementCheckOut(
            kind=c.kind,
            source=c.source,
            required_months=c.required_months,
            candidate_months=c.candidate_months,
            basis=c.basis,
            status=c.status,
            reason=c.reason,
            evidence=list(c.evidence),
        )
        for c in gate.checks
    ]
    deciding = next((c for c in checks if c.status == gate.status), checks[0] if checks else None)
    if deciding is None:
        return RequiredGateOut(status=gate.status, reason=gate.reason)
    return RequiredGateOut(
        status=gate.status, reason=deciding.reason, basis=deciding.basis, evidence=deciding.evidence, checks=checks
    )


def to_brief(gate: RequiredGate) -> RequiredGateBrief:
    return RequiredGateBrief(status=gate.status)
