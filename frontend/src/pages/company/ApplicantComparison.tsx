import { generatePath, Link, useParams } from 'react-router';
import { api, ApiError } from '@/api/client';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { cx, PageHead } from '@/components/common/Page';
import { GateDetail, hasGate } from '@/components/common/RequiredGate';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import { CandidateCv, CriterionEvidence } from '@/components/company/CandidateEvidence';
import s from '@/components/company/comparison.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { ApplicantRow, CriterionEvaluation, EvaluationOut } from '@/types/application';
import { topRankedPair } from './Applicants';

async function load(jobId: number) {
  const [job, ranking] = await Promise.all([api.job(jobId), api.applicants(jobId)]);
  const pair = topRankedPair(ranking);
  if (!pair) return { job, ranking, candidates: [] };
  const candidates = await Promise.all(pair.map(async row => ({ row, result: await api.evaluation(row.application_id) })));
  const consistent = ranking.job_id === jobId && candidates.every(({ row, result }) =>
    result.job_id === jobId && result.application_id === row.application_id && result.status === 'done' &&
    result.fit === row.fit && result.items.length === row.scores.length &&
    result.items.every(item =>
      row.scores.some(score => score.criterion_id === item.criterion_id && score.score === item.score) &&
      ranking.criteria.some(criterion => criterion.id === item.criterion_id && criterion.weight === item.weight)
    )
  );
  if (!consistent) throw new ApiError(409, 'COMPARISON_CHANGED', t('compare.changed'));
  return { job, ranking, candidates };
}

type Candidate = { row: ApplicantRow; result: EvaluationOut };

export default function ApplicantComparison() {
  const { jobId = '' } = useParams();
  return <Comparison key={jobId} jobId={jobId} />;
}

function Comparison({ jobId }: { jobId: string }) {
  const { state, reload } = useApi(() => load(Number(jobId)), [jobId]);
  const back = { to: generatePath(paths.company.applicants, { jobId }), label: t('jobTabs.applicants') };
  const data = state.status === 'ok' ? state.data : null;
  const [first, second] = data?.candidates ?? [];

  const rows = data?.ranking.criteria.map(criterion => ({
    criterion,
    left: first?.result.items.find(item => item.criterion_id === criterion.id),
    right: second?.result.items.find(item => item.criterion_id === criterion.id),
  })) ?? [];

  return (
    <div className={ui.page}>
      <PageHead title={t('compare.title')} lead={data?.job.title} back={back} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && (state.error instanceof ApiError && state.error.code === 'COMPARISON_CHANGED' ? (
        <Empty title={t('compare.changed')} action={<button type="button" className={cx(ui.btn, ui.secondary)} onClick={reload}>{t('common.refresh')}</button>} />
      ) : <ErrorPanel error={state.error} onRetry={reload} />)}
      {data && (!first || !second) && <Empty title={t('compare.notEnough')} action={<Link className={cx(ui.btn, ui.secondary)} to={back.to}>{back.label}</Link>} />}
      {data && first && second && (
        <div className={s.layout}>
          <div className={s.people}>
            {[first, second].map(candidate => (
              <section key={candidate.row.application_id} className={cx(ui.panel, s.person)}>
                <h2>{candidateLabel(candidate)}</h2>
                <p className={s.fit}>{candidate.result.fit?.toFixed(1)} <span>/ 100</span></p>
                <CandidateCv
                  applicationId={candidate.row.application_id}
                  jobId={candidate.result.job_id}
                  name={candidate.row.name}
                  quotes={candidate.result.items.flatMap(item => item.evidence)}
                />
                {hasGate(candidate.result.required_gate) && (
                  <details className={s.cv}>
                    <summary>{t('gate.title')}</summary>
                    <GateDetail gate={candidate.result.required_gate} audience="company" />
                    <p className={ui.caption}>{t('compare.gateNote')}</p>
                  </details>
                )}
              </section>
            ))}
          </div>
          <DifferenceSummary first={first} second={second} rows={rows} notice={data.ranking.notice} />
          <section className={cx(ui.panel, s.matrix)}>
            <h2>{t('compare.matrix')}</h2>
            {data.job.description && (
              <details className={s.cv}>
                <summary>{t('compare.jdSource')}</summary>
                <p className={s.cvText}>{data.job.description}</p>
              </details>
            )}
            <table role="table" className={s.table} aria-label={t('compare.matrix')}>
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">{t('compare.requirement')}</th>
                  <th role="columnheader" scope="col">{candidateLabel(first)}</th>
                  <th role="columnheader" scope="col">{candidateLabel(second)}</th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {rows.map(({ criterion, left, right }) => (
                  <tr role="row" key={criterion.id} id={evidenceId(criterion.id)} tabIndex={-1}>
                    <th role="rowheader" scope="row">
                      <strong>{criterion.name}</strong>
                      <p>{(left ?? right)?.description || t('compare.noRequirement')}</p>
                      <span className={ui.caption}>{t('compare.currentWeight', { n: criterion.weight })}</span>
                    </th>
                    <EvidenceCell candidate={first} item={left} />
                    <EvidenceCell candidate={second} item={right} />
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </div>
  );
}

type DifferenceRow = { criterion: { id: number; name: string; weight: number }; left?: CriterionEvaluation; right?: CriterionEvaluation };

const points = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const asNumber = (value: number | null | undefined) => typeof value === 'number' && Number.isFinite(value) ? value : null;

function DifferenceSummary({ first, second, rows, notice }: {
  first: Candidate; second: Candidate; rows: DifferenceRow[]; notice: string;
}) {
  const leftFit = first.result.fit ?? 0;
  const rightFit = second.result.fit ?? 0;
  const differences = rows.map(({ criterion, left, right }) => ({
    ...criterion,
    leftScore: left?.score,
    rightScore: right?.score,
    left: asNumber(left?.fit_contribution),
    right: asNumber(right?.fit_contribution),
  }));
  const leftTotal = differences.reduce((sum, row) => sum + (row.left ?? 0), 0);
  const rightTotal = differences.reduce((sum, row) => sum + (row.right ?? 0), 0);
  // The server rounds each overall Fit after summing its contributions.
  const weighted = differences.length > 0 && differences.every(row => row.left !== null && row.right !== null)
    && Math.abs(leftTotal - leftFit) <= 0.050001 && Math.abs(rightTotal - rightFit) <= 0.050001;
  const impacts = differences.map(row => ({
    ...row,
    gap: weighted && row.left !== null && row.right !== null ? row.left - row.right : null,
  })).sort((a, b) => Math.abs(b.gap ?? 0) - Math.abs(a.gap ?? 0));
  const tied = leftFit === rightFit;
  const lead = impacts.find(row => row.gap !== null && Math.abs(row.gap) >= 0.005);
  const counterpoint = impacts.find(row => row.gap !== null && row.gap <= -0.005 && row.id !== lead?.id);
  const firstName = first.row.name;
  const secondName = second.row.name;
  const difference = Math.abs(leftFit - rightFit).toFixed(1);
  const leadingName = (gap: number) => gap > 0 ? firstName : secondName;
  const scoreLabel = (score: number | undefined) => score === undefined ? '—' : t('apl.detail.score', { n: points.format(score) });
  const impactLabel = (gap: number | null) => gap === null ? t('compare.impactMissing')
    : Math.abs(gap) < 0.005 ? t('compare.impactEqual')
      : t('compare.impactLead', { name: leadingName(gap), n: points.format(Math.abs(gap)) });

  return (
    <section className={cx(ui.panel, s.summary)} aria-labelledby="fit-explanation-title">
      <h2 id="fit-explanation-title">{t('compare.explanationTitle')}</h2>
      <dl className={s.totals}>
        <div><dt>{firstName}</dt><dd>{t('apl.detail.score', { n: leftFit.toFixed(1) })}</dd></div>
        <div><dt>{secondName}</dt><dd>{t('apl.detail.score', { n: rightFit.toFixed(1) })}</dd></div>
        <div><dt>{t('compare.totalGapLabel')}</dt><dd>{t('apl.detail.score', { n: difference })}</dd></div>
      </dl>
      {tied && <p>{tieNote(first.row, second.row)}</p>}
      {lead && lead.gap !== null && (
        <div className={s.leadReason}>
          <div>
            <p className={s.leadPoints}>{t('compare.largestImpact', { criterion: lead.name })}</p>
            <p>{t('compare.leadScores', { first: firstName, firstScore: scoreLabel(lead.leftScore),
              second: secondName, secondScore: scoreLabel(lead.rightScore), weight: points.format(lead.weight) })}</p>
            <p>{t('compare.leadPoints', { name: leadingName(lead.gap), n: points.format(Math.abs(lead.gap)) })}</p>
          </div>
          <EvidenceLink criterion={lead} />
        </div>
      )}
      {counterpoint && counterpoint.gap !== null && (
        <div className={s.counterpoint}>
          <p>{counterpoint.name} · {impactLabel(counterpoint.gap)}</p>
          <EvidenceLink criterion={counterpoint} />
        </div>
      )}
      {!weighted && <p className={ui.caption}>{t('compare.rawNote')}</p>}
      <p className={s.impactIntro}>{t('compare.impactIntro')}</p>
      <table role="table" className={s.impactTable} aria-label={t('compare.impactTable')}>
        <thead role="rowgroup">
          <tr role="row">
            <th role="columnheader" scope="col">{t('compare.criterionColumn')}</th>
            <th role="columnheader" scope="col">{firstName}</th>
            <th role="columnheader" scope="col">{secondName}</th>
            <th role="columnheader" scope="col">{t('compare.weightColumn')}</th>
            <th role="columnheader" scope="col">{t('compare.impactColumn')}</th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {impacts.map(row => (
            <tr role="row" key={row.id} data-leading={row.id === lead?.id ? true : undefined}>
              <th role="rowheader" scope="row">{row.name}</th>
              <td role="cell"><span className={s.mobileLabel}>{firstName}</span><span>{scoreLabel(row.leftScore)}</span></td>
              <td role="cell"><span className={s.mobileLabel}>{secondName}</span><span>{scoreLabel(row.rightScore)}</span></td>
              <td role="cell"><span className={s.mobileLabel}>{t('compare.weightColumn')} </span>{points.format(row.weight)}%</td>
              <td role="cell" className={s.impactResult}>{impactLabel(row.gap)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details className={s.cv}>
        <summary>{t('compare.showCalculation')}</summary>
        {weighted ? (
          <>
            <ul className={s.calculationSteps}>
              {impacts.map(row => (
                <li key={row.id}><strong>{row.name}</strong>{' · '}
                  ({row.leftScore} − {row.rightScore}) × {points.format(row.weight)}% ≈ {t('apl.detail.score', { n: signed(row.gap ?? 0) })}
                </li>
              ))}
            </ul>
            <p>{t('compare.roundingDifference', {
              before: points.format(Math.abs(leftTotal - rightTotal)), left: leftFit.toFixed(1), right: rightFit.toFixed(1), after: difference,
            })}</p>
            <p className={ui.caption}>{t('compare.roundingNote')}</p>
          </>
        ) : <p className={ui.caption}>{t('compare.impactMissing')}</p>}
      </details>
      <AiNotice notice={notice} />
    </section>
  );
}

function EvidenceLink({ criterion }: { criterion: { id: number; name: string } }) {
  const id = evidenceId(criterion.id);
  return (
    <a className={cx(ui.btn, ui.secondary, ui.small)} href={`#${id}`}
      onClick={event => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const target = document.getElementById(id);
        if (!target) return;
        event.preventDefault();
        target.focus({ preventScroll: true });
        target.scrollIntoView({ block: 'start' });
      }}>
      {t('compare.evidenceLink', { criterion: criterion.name })}
    </a>
  );
}

function evidenceId(criterionId: number) {
  return `comparison-evidence-${criterionId}`;
}

function signed(value: number) {
  if (Math.abs(value) < 0.005) return '0';
  return `${value < 0 ? '−' : '+'}${points.format(Math.abs(value))}`;
}

function tieNote(first: ApplicantRow, second: ApplicantRow) {
  if (first.strong_count > second.strong_count) {
    return t('compare.tieStrong', { first: first.strong_count, second: second.strong_count });
  }
  if (first.strong_count === second.strong_count && Date.parse(first.applied_at) < Date.parse(second.applied_at)) {
    return t('compare.tieEarlier');
  }
  return t('compare.tie');
}

function candidateLabel({ row }: Candidate) {
  return t('compare.candidate', { rank: row.rank ?? '—', name: row.name });
}

function EvidenceCell({ candidate, item }: { candidate: Candidate; item?: CriterionEvaluation }) {
  return (
    <td role="cell">
      <strong className={s.mobileName}>{candidateLabel(candidate)}</strong>
      {item ? (
        <>
          <p className={s.criterionScore}>{item.score} <span>/ 100</span></p>
          <CriterionEvidence item={item} />
        </>
      ) : <p className={ui.caption}>{t('compare.noScore')}</p>}
    </td>
  );
}
