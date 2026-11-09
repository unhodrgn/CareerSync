// Display decisions around the required criteria gate (D50), kept free of React and i18n so they can be unit-tested
// with Node's built-in test runner (frontend/tests/gateDisplay.test.ts). Components turn the result into text with t().
import type { GateStatusT, RequiredGateOut, RequirementCheckOut } from '@/types/gate';
import type { JobMatch } from '@/types/recommendation';

/** The check the gate's status comes from (the MVP has at most one). */
export function decidingCheck(gate: RequiredGateOut | null | undefined): RequirementCheckOut | undefined {
  if (!gate || !Array.isArray(gate.checks) || gate.checks.length === 0) return undefined;
  return gate.checks.find((c) => c.status === gate.status) ?? gate.checks[0];
}

/**
 * Which experience an applicant row shows. `experience_months` is read from employment periods only, so for a CV
 * that states its total without periods it is 0; when the gate used that stated total (basis `stated`), show it
 * labelled as stated and unverified instead of a 0 that contradicts the gate. Otherwise keep the period value as before
 * (also without a gate, or without a check: nothing is made up).
 */
export type ExperienceDisplay = { kind: 'stated'; months: number } | { kind: 'periods'; months: number };

export function experienceDisplay(experienceMonths: number, gate: RequiredGateOut | null | undefined): ExperienceDisplay {
  const check = decidingCheck(gate);
  if (check && check.basis === 'stated' && typeof check.candidate_months === 'number' && Number.isFinite(check.candidate_months) && check.candidate_months >= 0) {
    return { kind: 'stated', months: check.candidate_months };
  }
  return { kind: 'periods', months: experienceMonths };
}

/**
 * A duration as a message key and its values: "2년", "1년 6개월", "5개월". A stated total of zero reads "0년", as the
 * CV and the gate's reason write it; a period-based zero stays "0개월" as before.
 */
export type DurationText =
  | { key: 'common.yearsShort'; vars: { n: number } }
  | { key: 'common.months'; vars: { y: number; m: number } }
  | { key: 'common.monthsOnly'; vars: { m: number } };

export function durationText(months: number, stated = false): DurationText {
  const y = Math.floor(months / 12);
  const m = months % 12;
  if (y === 0 && m === 0 && stated) return { key: 'common.yearsShort', vars: { n: 0 } };
  if (y === 0) return { key: 'common.monthsOnly', vars: { m } };
  return m === 0 ? { key: 'common.yearsShort', vars: { n: y } } : { key: 'common.months', vars: { y, m } };
}

/**
 * What the job detail match box says (D43, D50), in the order the page has always used: a done score first, then a
 * running evaluation, then an applied job. Only when none of these holds and the gate is FAIL does it say that no
 * recommendation analysis runs for this job (a FAIL job is never queued) instead of promising a score later.
 */
export type MatchView = 'score' | 'pending' | 'applied' | 'gateFail' | 'noScore';

export function matchView(match: Pick<JobMatch, 'status' | 'required_gate'> | null | undefined, hasScore: boolean, applied: boolean): MatchView {
  if (match?.status === 'done' && hasScore) return 'score';
  if (match?.status === 'pending' && !applied) return 'pending';
  if (applied) return 'applied';
  const status: GateStatusT | undefined = match?.required_gate?.status;
  if (status === 'FAIL') return 'gateFail';
  return 'noScore';
}
