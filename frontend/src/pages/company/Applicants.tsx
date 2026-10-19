import { useState, type KeyboardEvent } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate, monthsLabel } from '@/components/common/format';
import { RefreshIcon } from '@/components/common/icons';
import { ApplicationStatusTag, ScoreSquare } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import ApplicantDetail from '@/components/company/ApplicantDetail';
import JobHeader from '@/components/company/JobHeader';
import s from '@/components/company/company.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { APPLICATION_STATUSES, type ApplicantList, type ApplicationStatus, type EvaluationStatus } from '@/types/application';

const MIN_FITS = [60, 70, 80];
const EVAL_STATUSES: EvaluationStatus[] = ['done', 'pending', 'failed'];

/**
 * Applicants ranked by Fit (D22): the quick filters apply after ranking, so a rank never shifts. The selected
 * applicant (`?selected=`) opens beside the table with the evaluation and the status buttons.
 */
export default function Applicants() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const job = useApi(() => api.job(id), [id]);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus[]>([]);
  const [minFit, setMinFit] = useState<number | undefined>(undefined);
  const [evalFilter, setEvalFilter] = useState<EvaluationStatus | undefined>(undefined);
  const list = useApi(
    () => api.applicants(id, { status: statusFilter, min_fit: minFit, evaluation_status: evalFilter }),
    [id, statusFilter.join(','), minFit, evalFilter],
  );
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get('selected')) || null;
  const select = (applicationId: number) => setParams({ selected: String(applicationId) }, { replace: true });

  if (job.state.status === 'loading') {
    return (
      <div className={ui.page}>
        <Loading rows={8} />
      </div>
    );
  }
  if (job.state.status === 'error') {
    return (
      <div className={ui.page}>
        <PageHead title={t('page.company.applicants.title')} back={{ to: paths.company.jobs, label: t('jobTabs.back') }} />
        <ErrorPanel error={job.state.error} onRetry={job.reload} />
      </div>
    );
  }

  const filtered = statusFilter.length > 0 || minFit !== undefined || evalFilter !== undefined;
  return (
    <div className={ui.page} style={{ maxWidth: 1360 }}>
      <JobHeader job={job.state.data} />
      <div className={s.filters}>
        <span className={s.filterGroup} role="group" aria-label={t('apl.filter.status')}>
          {t('apl.filter.status')}
          {APPLICATION_STATUSES.map((x) => (
            <button
              key={x}
              type="button"
              className={s.toggle}
              aria-pressed={statusFilter.includes(x)}
              onClick={() => setStatusFilter((f) => (f.includes(x) ? f.filter((y) => y !== x) : [...f, x]))}
            >
              {t(`appStatus.${x}`)}
            </button>
          ))}
        </span>
        <label className={s.filterGroup}>
          {t('apl.filter.minFit')}
          <select className={cx(ui.select, s.smallSelect)} value={minFit ?? ''} onChange={(e) => setMinFit(e.target.value ? Number(e.target.value) : undefined)}>
            <option value="">{t('apl.filter.all')}</option>
            {MIN_FITS.map((n) => (
              <option key={n} value={n}>
                {t('apl.filter.minFitValue', { n })}
              </option>
            ))}
          </select>
        </label>
        <label className={s.filterGroup}>
          {t('apl.filter.eval')}
          <select
            className={cx(ui.select, s.smallSelect)}
            value={evalFilter ?? ''}
            onChange={(e) => setEvalFilter((e.target.value || undefined) as EvaluationStatus | undefined)}
          >
            <option value="">{t('apl.filter.all')}</option>
            {EVAL_STATUSES.map((x) => (
              <option key={x} value={x}>
                {t(`evalStatus.${x}`)}
              </option>
            ))}
          </select>
        </label>
        {filtered && (
          <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={() => (setStatusFilter([]), setMinFit(undefined), setEvalFilter(undefined))}>
            {t('apl.filter.reset')}
          </button>
        )}
      </div>

      {list.state.status === 'loading' && <Loading rows={6} />}
      {list.state.status === 'error' && <ErrorPanel error={list.state.error} onRetry={list.reload} />}
      {list.state.status === 'ok' && (
        <Board data={list.state.data} selected={selected} onSelect={select} onRefresh={list.reload} setData={list.setData} filtered={filtered} />
      )}
    </div>
  );
}

function Board({
  data,
  selected,
  onSelect,
  onRefresh,
  setData,
  filtered,
}: {
  data: ApplicantList;
  selected: number | null;
  onSelect: (id: number) => void;
  onRefresh: () => void;
  setData: (d: ApplicantList) => void;
  filtered: boolean;
}) {
  if (data.total_count === 0) return <Empty title={t('apl.empty.title')} body={t('apl.empty.body')} />;
  const current = data.items.find((r) => r.application_id === selected) ?? null;
  const onKey = (e: KeyboardEvent, applicationId: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(applicationId);
    }
  };
  const pending = data.items.some((r) => r.evaluation_status === 'pending');

  return (
    <div className={s.board}>
      <section className={ui.panel} aria-labelledby="ranking-title">
        <div className={s.tableHead}>
          <h2 id="ranking-title" className={ui.panelTitle}>
            {t('apl.total', { shown: data.items.length, total: data.total_count })}
          </h2>
          {pending && (
            <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={onRefresh}>
              <RefreshIcon width={15} height={15} />
              {t('common.refresh')}
            </button>
          )}
        </div>
        <AiNotice notice={data.notice} />
        {filtered && <p className={ui.caption}>{t('apl.filter.note')}</p>}
        {data.items.length === 0 ? (
          <Empty panel={false} title={t('apl.noMatch')} />
        ) : (
          <table className={ui.table} style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>{t('apl.col.rank')}</th>
                <th>{t('apl.col.name')}</th>
                {data.criteria.map((c) => (
                  <th key={c.id} className={s.critHead} title={c.name}>
                    <span className={s.critHeadName}>{c.name}</span>
                    <span className={s.critHeadWeight}>{Math.round(c.weight)}%</span>
                  </th>
                ))}
                <th style={{ textAlign: 'right' }}>{t('apl.col.fit')}</th>
              </tr>
            </thead>
            <tbody className={ui.stagger}>
              {data.items.map((a) => (
                <tr
                  key={a.application_id}
                  className={s.applicantRow}
                  tabIndex={0}
                  aria-selected={selected === a.application_id}
                  onClick={() => onSelect(a.application_id)}
                  onKeyDown={(e) => onKey(e, a.application_id)}
                >
                  <td>{a.rank ? <span className={s.rank} data-top={a.rank === 1 || undefined}>{a.rank}</span> : <span className={ui.muted}>—</span>}</td>
                  <td>
                    <span className={s.nameCell}>
                      <strong>{a.name}</strong>
                      <span className={ui.caption}>
                        <ApplicationStatusTag status={a.status} />
                        {' · '}
                        {a.evaluation_status === 'done'
                          ? t('apl.experience', { value: monthsLabel(a.experience_months) })
                          : t('apl.applied', { date: formatDate(a.applied_at) })}
                      </span>
                    </span>
                  </td>
                  {data.criteria.map((c) => {
                    const sc = a.scores.find((x) => x.criterion_id === c.id);
                    return (
                      <td key={c.id} className={s.scoreCell}>
                        {sc ? (
                          <span className={s.score}>
                            <ScoreSquare score={sc.score} />
                            {sc.score}
                          </span>
                        ) : a.evaluation_status === 'pending' ? (
                          <span className={ui.skeleton} style={{ display: 'inline-block', width: 28, height: 10 }} />
                        ) : (
                          <span className={ui.muted}>—</span>
                        )}
                      </td>
                    );
                  })}
                  <td style={{ textAlign: 'right' }}>
                    {a.fit !== null ? <span className={s.fit}>{a.fit.toFixed(1)}</span> : <span className={ui.caption}>{t(`evalStatus.${a.evaluation_status}`)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data.excluded_criteria.length > 0 && (
          <p className={ui.caption} style={{ marginTop: 12 }}>
            {t('apl.detail.excluded', { names: data.excluded_criteria.map((c) => c.name).join(', ') })}
          </p>
        )}
      </section>

      {current ? (
        <ApplicantDetail
          key={current.application_id}
          row={current}
          criteriaCount={data.criteria.length}
          onStatusChanged={(status) => setData({ ...data, items: data.items.map((r) => (r.application_id === current.application_id ? { ...r, status } : r)) })}
          onEvaluationChanged={onRefresh}
        />
      ) : (
        <aside className={cx(ui.panel, s.detail)}>
          <p className={ui.caption}>{t('apl.select')}</p>
        </aside>
      )}
    </div>
  );
}
