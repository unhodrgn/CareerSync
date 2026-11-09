// Unit tests for the gate display decisions (D50), with Node's built-in test runner: no dependency.
// Run: node --test frontend/tests/   (Node 22.18+ / 23.6+ runs TypeScript directly; backend/tests/test_frontend_node_unit.py
// runs this as part of pytest). Outside src/, so tsc -b and the Vite bundle never see it.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import { decidingCheck, durationText, experienceDisplay, matchView } from '../src/components/common/gateDisplay.ts';
import type { GateBasisT, GateStatusT, RequiredGateOut } from '../src/types/gate.ts';

function gate(status: GateStatusT, basis: GateBasisT | null, candidate: number | null, required = 36): RequiredGateOut {
  return {
    status,
    reason: 'reason',
    basis,
    evidence: basis ? ['line'] : [],
    checks: [
      { kind: 'min_experience', source: 'job.min_experience_years', required_months: required, candidate_months: candidate, basis, status, reason: 'reason', evidence: [] },
    ],
  };
}
const noMinimum: RequiredGateOut = { status: 'PASS', reason: '필수 경력 조건 없음', basis: null, evidence: [], checks: [] };

describe('experienceDisplay (applicant list and detail)', () => {
  test('stated 5 years with period-based 0 shows the stated total, not 0', () => {
    assert.deepEqual(experienceDisplay(0, gate('PASS', 'stated', 60)), { kind: 'stated', months: 60 });
  });

  test('stated 0 years against a minimum shows a stated 0', () => {
    assert.deepEqual(experienceDisplay(0, gate('FAIL', 'stated', 0)), { kind: 'stated', months: 0 });
  });

  test('period-based experience is unchanged', () => {
    assert.deepEqual(experienceDisplay(69, gate('PASS', 'periods', 69)), { kind: 'periods', months: 69 });
    // Periods conflicting with a stated total (REVIEW, basis periods): still the period value
    assert.deepEqual(experienceDisplay(24, gate('REVIEW', 'periods', 24)), { kind: 'periods', months: 24 });
  });

  test('null, missing or check-less gates keep the existing period value', () => {
    for (const g of [null, undefined, noMinimum]) assert.deepEqual(experienceDisplay(0, g), { kind: 'periods', months: 0 });
  });

  test('no experience information (REVIEW, basis null) makes nothing up', () => {
    assert.deepEqual(experienceDisplay(0, gate('REVIEW', null, null)), { kind: 'periods', months: 0 });
  });

  test('a malformed candidate value is ignored', () => {
    const bad = gate('PASS', 'stated', 60);
    bad.checks[0].candidate_months = Number.NaN;
    assert.deepEqual(experienceDisplay(0, bad), { kind: 'periods', months: 0 });
    bad.checks[0].candidate_months = -12;
    assert.deepEqual(experienceDisplay(0, bad), { kind: 'periods', months: 0 });
  });

  test('the deciding check is the one with the gate status', () => {
    const g = gate('FAIL', 'stated', 0);
    g.checks.unshift({ ...g.checks[0], status: 'PASS', candidate_months: 99 });
    assert.equal(decidingCheck(g)?.candidate_months, 0);
    assert.equal(decidingCheck(noMinimum), undefined);
  });
});

describe('durationText (one format for list, detail and the gate block)', () => {
  test('a stated zero reads 0년, a period-based zero 0개월', () => {
    assert.deepEqual(durationText(0, true), { key: 'common.yearsShort', vars: { n: 0 } });
    assert.deepEqual(durationText(0), { key: 'common.monthsOnly', vars: { m: 0 } });
  });

  test('years, years and months, months only', () => {
    assert.deepEqual(durationText(60, true), { key: 'common.yearsShort', vars: { n: 5 } });
    assert.deepEqual(durationText(69), { key: 'common.months', vars: { y: 5, m: 9 } });
    assert.deepEqual(durationText(5), { key: 'common.monthsOnly', vars: { m: 5 } });
  });
});

describe('matchView (job detail match box)', () => {
  const m = (status: 'done' | 'pending' | 'none', g: RequiredGateOut | null = null) => ({ status, required_gate: g });

  test('FAIL with no score says no recommendation analysis runs', () => {
    assert.equal(matchView(m('none', gate('FAIL', 'stated', 0)), false, false), 'gateFail');
  });

  test('FAIL with an existing score keeps the score', () => {
    assert.equal(matchView(m('done', gate('FAIL', 'stated', 0)), true, false), 'score');
  });

  test('a running evaluation keeps its message, whatever the gate', () => {
    assert.equal(matchView(m('pending', gate('PASS', 'stated', 60)), false, false), 'pending');
    assert.equal(matchView(m('pending', gate('FAIL', 'stated', 0)), false, false), 'pending');
  });

  test('REVIEW and PASS without a score keep the existing message', () => {
    assert.equal(matchView(m('none', gate('REVIEW', null, null)), false, false), 'noScore');
    assert.equal(matchView(m('none', gate('PASS', 'stated', 60)), false, false), 'noScore');
  });

  test('a null gate keeps the existing behaviour', () => {
    assert.equal(matchView(m('none'), false, false), 'noScore');
    assert.equal(matchView(null, false, false), 'noScore');
  });

  test('an applied job keeps its message (the backend sends no gate then)', () => {
    assert.equal(matchView(m('none'), false, true), 'applied');
    assert.equal(matchView(m('pending'), false, true), 'applied');
  });

  test('a done status without a valid score is not shown as a score', () => {
    assert.equal(matchView(m('done', gate('FAIL', 'stated', 0)), false, false), 'gateFail');
    assert.equal(matchView(m('done'), false, false), 'noScore');
  });
});
