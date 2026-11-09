import { t } from '@/i18n';
import type { GateBasisT, GateStatusT, RequiredGateBrief, RequiredGateOut } from '@/types/gate';
import { durationText, experienceDisplay } from './gateDisplay';
import ui from './ui.module.css';

// The required criteria gate (D50): a status about the job's minimum experience, shown apart from Fit and the match
// score. It is a recommendation filter, never a rejection, so every wording here goes through t() and none says the
// AI turned anyone down.

const STATUSES: readonly GateStatusT[] = ['PASS', 'FAIL', 'REVIEW'];

/** A status the frontend knows; anything else (missing, null, another backend version) shows nothing. */
export function isGateStatus(value: unknown): value is GateStatusT {
  return typeof value === 'string' && (STATUSES as readonly string[]).includes(value);
}

/**
 * Whether there is anything to show: a full gate with at least one check (a job without a minimum is PASS with no
 * check, and saying 충족 there would claim a requirement that does not exist), or a status-only gate for a job that
 * sets a minimum (the talent card, which gets no checks).
 */
export function hasGate(gate: RequiredGateOut | null | undefined): gate is RequiredGateOut {
  return gate != null && isGateStatus(gate.status) && Array.isArray(gate.checks) && gate.checks.length > 0;
}

export function hasBriefGate(gate: RequiredGateBrief | null | undefined, minExperienceYears: number | null | undefined): gate is RequiredGateBrief {
  return gate != null && isGateStatus(gate.status) && typeof minExperienceYears === 'number' && minExperienceYears > 0;
}

/** A duration for the gate: a stated zero reads 0년, as the CV and the reason write it (see `durationText`). */
export function gateDuration(months: number, stated = false): string {
  const d = durationText(months, stated);
  return t(d.key, d.vars);
}

/**
 * The experience an applicant row or detail shows: the period-based months as before, or — when the gate used the CV's
 * stated total because it has no employment period — that total, labelled as stated with the periods unverified.
 */
export function applicantExperience(experienceMonths: number, gate: RequiredGateOut | null | undefined): string {
  const shown = experienceDisplay(experienceMonths, gate);
  return shown.kind === 'stated'
    ? t('apl.experienceStated', { value: gateDuration(shown.months, true) })
    : t('apl.experience', { value: gateDuration(shown.months) });
}

export function gateLabel(status: GateStatusT): string {
  return t(`gate.status.${status}`);
}

/**
 * The gate as a status tag (dot + words; the words always say which, so the color never carries the meaning alone).
 * `short` drops "최소 경력 조건" for a table cell whose column header already says it; the full label stays the
 * tag's accessible name.
 */
export function GateTag({ status, short = false }: { status: GateStatusT; short?: boolean }) {
  return (
    <span className={ui.status} data-gate={status} aria-label={short ? t('gate.cellLabel', { status: gateLabel(status) }) : undefined}>
      {short ? t(`gate.short.${status}`) : gateLabel(status)}
    </span>
  );
}

const BASIS: Record<GateBasisT, { label: 'gate.basis.periods' | 'gate.basis.stated'; note: 'gate.basisNote.periods' | 'gate.basisNote.stated' }> = {
  periods: { label: 'gate.basis.periods', note: 'gate.basisNote.periods' },
  stated: { label: 'gate.basis.stated', note: 'gate.basisNote.stated' },
};

/**
 * The full gate result: status, the minimum, the experience the decision used, its basis (employment periods, or the
 * total the CV states — then the periods are not verified), the reason and the CV lines. `seeker` adds the notice that
 * applying stays possible; `company` adds that the label changes no status or rank. Callers check `hasGate` first.
 */
export function GateDetail({ gate, audience }: { gate: RequiredGateOut; audience: 'seeker' | 'company' }) {
  const check = gate.checks.find((c) => c.status === gate.status) ?? gate.checks[0];
  const basis = gate.basis ?? check?.basis ?? null;
  const evidence = Array.isArray(gate.evidence) ? gate.evidence : [];
  return (
    <div className={ui.stack} style={{ gap: 8 }}>
      <GateTag status={gate.status} />
      {check && (
        <dl className={ui.facts}>
          <dt>{t('gate.required')}</dt>
          <dd>{gateDuration(check.required_months)}</dd>
          <dt>{t('gate.candidate')}</dt>
          <dd>{check.candidate_months == null ? t('gate.candidateNone') : gateDuration(check.candidate_months, basis === 'stated')}</dd>
          <dt>{t('gate.basis')}</dt>
          <dd>{basis ? t(BASIS[basis].label) : t('gate.basis.none')}</dd>
        </dl>
      )}
      <p className={ui.caption}>{basis ? t(BASIS[basis].note) : t('gate.basisNote.none')}</p>
      {gate.reason && <p className={ui.body}>{gate.reason}</p>}
      {evidence.length > 0 && (
        <div className={ui.stack} style={{ gap: 4 }}>
          <span className={ui.caption}>{t('gate.evidence')}</span>
          {evidence.map((line, i) => (
            <p key={i} className={ui.quote}>
              {line}
            </p>
          ))}
        </div>
      )}
      {audience === 'seeker' && gate.status === 'FAIL' && <p className={ui.notice}>{t('gate.seeker.fail')}</p>}
      {audience === 'seeker' && gate.status === 'REVIEW' && <p className={ui.caption}>{t('gate.seeker.review')}</p>}
      {audience === 'company' && <p className={ui.caption}>{t('gate.company.note')}</p>}
    </div>
  );
}
