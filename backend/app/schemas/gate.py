"""Required criteria gate in API responses (docs/DECISIONS.md D50), built from `ai.scoring.gate.RequiredGate`."""
from typing import Literal

from pydantic import BaseModel, Field

GateStatusT = Literal["PASS", "FAIL", "REVIEW"]
GateBasisT = Literal["periods", "stated"]


class RequirementCheckOut(BaseModel):
    kind: str = Field(description="min_experience (the only kind in the MVP)")
    source: str = Field(description="Where the requirement comes from: job.min_experience_years")
    required_months: int
    candidate_months: int | None = Field(description="Experience the decision used; null when the CV gives none")
    basis: GateBasisT | None = Field(description="periods = employment periods in the CV text; stated = the CV's stated total")
    status: GateStatusT
    reason: str
    evidence: list[str] = Field(description="CV lines the decision rests on")


class RequiredGateOut(BaseModel):
    """Gate status next to Fit, never part of it. A recommendation filter, not a hiring decision: FAIL never changes
    an application. `reason`, `basis` and `evidence` repeat the deciding check (the MVP has at most one); with no
    minimum set the status is PASS with no checks."""

    status: GateStatusT
    reason: str
    basis: GateBasisT | None = None
    evidence: list[str] = []
    checks: list[RequirementCheckOut] = []


class RequiredGateBrief(BaseModel):
    """Status only, for the anonymous talent card: reasons, months and evidence would quote the CV (D19, issue 24)."""

    status: GateStatusT
