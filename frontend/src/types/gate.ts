// Mirrors backend/app/schemas/gate.py: the required criteria gate (D50), a status next to Fit, never part of it.
// backend/tests/test_required_gate_frontend.py fails if these fields drift from the backend schemas.

export type GateStatusT = 'PASS' | 'FAIL' | 'REVIEW';
/** periods = employment periods in the CV text; stated = the total the CV states (not verified by periods). */
export type GateBasisT = 'periods' | 'stated';

export const GATE_STATUSES: GateStatusT[] = ['PASS', 'FAIL', 'REVIEW'];

export interface RequirementCheckOut {
  /** min_experience (the only kind in the MVP). */
  kind: string;
  /** Where the requirement comes from: job.min_experience_years. */
  source: string;
  required_months: number;
  /** The experience the decision used; null when the CV gives none. */
  candidate_months: number | null;
  basis: GateBasisT | null;
  status: GateStatusT;
  reason: string;
  /** CV lines the decision rests on. */
  evidence: string[];
}

/** Recruiter (applicant list, evaluation) and seeker (recommended jobs, job detail) responses. */
export interface RequiredGateOut {
  status: GateStatusT;
  reason: string;
  basis: GateBasisT | null;
  evidence: string[];
  /** Empty when the job sets no minimum (PASS without a check). */
  checks: RequirementCheckOut[];
}

/** The anonymous talent card: status only, never a reason, months or CV lines (D19). */
export interface RequiredGateBrief {
  status: GateStatusT;
}
