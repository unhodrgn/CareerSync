import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router';
import { CheckIcon, InfoIcon } from '@/components/common/icons';
import {
  APPLICANTS,
  APPLICATION_STATUSES,
  COMPANY_USER,
  fitOf,
  formatDate,
  jobById,
  STRONG_SCORE,
  type Applicant,
  type ApplicationStatus,
  type Criterion,
  type EvaluationStatus,
} from '../data';
import { t } from '../i18n';
import { RefreshIcon } from '../icons';
import { AiNotice, CategoryTag, cx, Example, monthsLabel, ui } from '../ui';
import JobTabs from './JobTabs';
import s from './company.module.css';

export const scoreLevel = (score: number) => (score >= STRONG_SCORE ? 'met' : score >= 40 ? 'partial' : 'missing');

interface Ranked extends Applicant {
  rank: number | null;
  fit: number | null;
}

/** GET /api/jobs/{id}/applications: ranked by Fit over all applicants, then filtered (D22), so ranks never shift. */
export default function Applicants() {
  const { jobId } = useParams();
  const job = jobById(Number(jobId)) ?? jobById(101)!;
  const criteria = job.criteria;
  const [rows, setRows] = useState<Applicant[]>(job.id === 101 ? APPLICANTS : []);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus[]>([]);
  const [minFit, setMinFit] = useState(0);
  const [evalFilter, setEvalFilter] = useState<EvaluationStatus | ''>('');
  const [selected, setSelected] = useState<number | null>(rows[0]?.application_id ?? null);
  const [hover, setHover] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const [changed, setChanged] = useState<Record<number, ApplicationStatus>>({});
  const active = hover ?? pinned;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPinned(null);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const ranked: Ranked[] = useMemo(() => {
    const withFit = rows.map((a) => ({ ...a, fit: fitOf(a, criteria), rank: null as number | null }));
    const done = withFit.filter((a) => a.fit !== null).sort((a, b) => b.fit! - a.fit!);
    done.forEach((a, i) => (a.rank = i + 1));
    return [...done, ...withFit.filter((a) => a.fit === null)];
  }, [rows, criteria]);

  const shown = ranked.filter(
    (a) =>
      (statusFilter.length === 0 || statusFilter.includes(a.status)) &&
      (minFit === 0 || (a.fit !== null && a.fit >= minFit)) &&
      (!evalFilter || a.evaluation_status === evalFilter),
  );
  const current = ranked.find((a) => a.application_id === selected) ?? null;

  const setStatus = (id: number, status: ApplicationStatus) => {
    setRows((rs) => rs.map((r) => (r.application_id === id ? { ...r, status } : r)));
    setChanged((c) => ({ ...c, [id]: status }));
  };

  return (
    <div className={ui.page} style={{ maxWidth: 1480 }}>
      <JobTabs job={job} />

      <div className={s.filters}>
        <span className={s.filterGroup}>
          {t('app.filter.status')}
          {APPLICATION_STATUSES.map((x) => (
            <button
              key={x}
              type="button"
              className={s.toggleChip}
              aria-pressed={statusFilter.includes(x)}
              onClick={() => setStatusFilter((f) => (f.includes(x) ? f.filter((y) => y !== x) : [...f, x]))}
            >
              {t(`appStatus.${x}`)}
            </button>
          ))}
        </span>
        <label className={s.filterGroup}>
          {t('app.filter.minFit')}
          <select className={cx(ui.select, s.smallSelect)} style={{ width: 110 }} value={minFit} onChange={(e) => setMinFit(Number(e.target.value))}>
            <option value={0}>{t('app.filter.minFitAll')}</option>
            {[60, 70, 80].map((n) => (
              <option key={n} value={n}>
                {t('app.filter.minFitValue', { n })}
              </option>
            ))}
          </select>
        </label>
        <label className={s.filterGroup}>
          {t('app.filter.eval')}
          <select className={cx(ui.select, s.smallSelect)} style={{ width: 120 }} value={evalFilter} onChange={(e) => setEvalFilter(e.target.value as EvaluationStatus | '')}>
            <option value="">{t('app.filter.evalAll')}</option>
            {(['done', 'pending', 'failed'] as const).map((x) => (
              <option key={x} value={x}>
                {t(`evalStatus.${x}`)}
              </option>
            ))}
          </select>
        </label>
        {(statusFilter.length > 0 || minFit > 0 || evalFilter) && (
          <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={() => (setStatusFilter([]), setMinFit(0), setEvalFilter(''))}>
            {t('app.filter.reset')}
          </button>
        )}
        <span className={ui.caption} style={{ marginLeft: 'auto' }}>
          {t('app.filter.note')}
        </span>
      </div>

      <div className={s.board}>
        <section className={s.tableWrap}>
          <div className={s.tableHead}>
            <h2 className={ui.panelTitle}>
              {t('app.total', { shown: shown.length, total: ranked.length })}
              <Example />
            </h2>
            <span className={ui.caption}>{t('app.colHint')}</span>
          </div>
          <AiNotice method="rules" />
          <table className={cx(ui.table, s.table)} data-active={active !== null || undefined} style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>{t('app.col.rank')}</th>
                <th>{t('app.col.name')}</th>
                {criteria.map((c) => (
                  <th key={c.id} style={{ textAlign: 'center', padding: '0 4px 8px' }}>
                    <button
                      type="button"
                      className={s.critHead}
                      data-lit={active === c.id || undefined}
                      aria-pressed={pinned === c.id}
                      title={c.name}
                      onMouseEnter={() => setHover(c.id)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(c.id)}
                      onBlur={() => setHover(null)}
                      onClick={() => setPinned((p) => (p === c.id ? null : c.id))}
                    >
                      {shortName(c)}
                      <span className={s.critHeadWeight}>{c.weight}%</span>
                    </button>
                  </th>
                ))}
                <th style={{ textAlign: 'right' }}>{t('app.col.fit')}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((a) => (
                <tr
                  key={a.application_id}
                  className={s.applicantRow}
                  aria-selected={selected === a.application_id}
                  tabIndex={0}
                  onClick={() => setSelected(a.application_id)}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setSelected(a.application_id))}
                >
                  <td>{a.rank ? <span className={s.rank} data-top={a.rank === 1 || undefined}>{a.rank}</span> : <span className={ui.muted}>—</span>}</td>
                  <td>
                    <span className={s.nameCell}>
                      <strong>
                        {a.name}{' '}
                        <span className={ui.status} data-status={a.status} style={{ marginLeft: 6, fontSize: 12 }}>
                          {t(`appStatus.${a.status}`)}
                        </span>
                      </strong>
                      <span className={ui.caption}>
                        {a.evaluation_status === 'done'
                          ? t('app.experience', { value: monthsLabel(a.experience_months) })
                          : t('app.applied', { date: formatDate(a.applied_at) })}
                      </span>
                    </span>
                  </td>
                  {criteria.map((c) => {
                    const item = a.items.find((i) => i.criterion_id === c.id);
                    return (
                      <td key={c.id} className={s.scoreCell} data-lit={active === c.id || undefined}>
                        {item ? (
                          <span className={s.score}>
                            <span className={s.square} data-level={scoreLevel(item.score)} />
                            {item.score}
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
          {shown.length === 0 && (
            <div className={ui.empty}>
              <p className={ui.emptyBody}>{t('app.noMatch')}</p>
            </div>
          )}
        </section>

        <ApplicantDetail
          key={current?.application_id ?? 'none'}
          applicant={current}
          criteria={criteria}
          active={active}
          changedTo={current ? changed[current.application_id] : undefined}
          onStatus={setStatus}
        />
      </div>
    </div>
  );
}

function shortName(c: Criterion) {
  const name = c.name.replace(/ (활용 능력|경험|관련 전공|운영 경험)$/u, '');
  return name.length > 8 ? `${name.slice(0, 7)}…` : name;
}

function ApplicantDetail({
  applicant: a,
  criteria,
  active,
  changedTo,
  onStatus,
}: {
  applicant: Ranked | null;
  criteria: Criterion[];
  active: number | null;
  changedTo?: ApplicationStatus;
  onStatus: (id: number, s: ApplicationStatus) => void;
}) {
  const [retried, setRetried] = useState(false);
  if (!a) {
    return (
      <aside className={s.detail}>
        <p className={ui.caption}>{t('app.select')}</p>
      </aside>
    );
  }
  const met = a.items.filter((i) => i.score >= STRONG_SCORE).length;

  return (
    <aside className={s.detail} aria-label={a.name}>
      <div className={s.detailHead}>
        <div>
          <h2 className={s.detailName}>{a.name}</h2>
          <p className={ui.caption}>{a.email}</p>
          <p className={ui.caption}>{t('app.applied', { date: formatDate(a.applied_at) })}</p>
        </div>
        {a.fit !== null && (
          <div className={s.fitBlock}>
            <span className={ui.caption}>{t('app.detail.fit')}</span>
            <span className={s.fitBig}>{a.fit.toFixed(1)}</span>
            <span className={ui.caption}>{t('app.detail.met', { total: criteria.length, n: met })}</span>
          </div>
        )}
      </div>

      <div className={s.statusBox}>
        <span className={ui.label}>{t('app.detail.status')}</span>
        <div className={s.statusGrid} role="radiogroup" aria-label={t('app.detail.status')}>
          {APPLICATION_STATUSES.map((x) => (
            <button key={x} type="button" role="radio" aria-checked={a.status === x} className={s.statusOption} onClick={() => onStatus(a.application_id, x)}>
              {t(`appStatus.${x}`)}
            </button>
          ))}
        </div>
        {changedTo ? (
          <span className={ui.done} role="status" style={{ fontSize: 12.5 }}>
            <CheckIcon width={14} height={14} />
            {t('app.detail.statusChanged', { status: t(`appStatus.${changedTo}`), who: COMPANY_USER.display_name })}
          </span>
        ) : (
          <span className={ui.caption}>{t('app.detail.statusNote')}</span>
        )}
      </div>

      {a.evaluation_status === 'pending' && (
        <p className={ui.aiNotice}>
          <InfoIcon width={16} height={16} />
          {t('app.detail.pending')}
        </p>
      )}
      {a.evaluation_status === 'failed' && (
        <div className={ui.inlineConfirm}>
          <span>{t('app.detail.failed')}</span>
          {retried ? (
            <span className={ui.done}>
              <CheckIcon width={14} height={14} />
              {t('app.retrying')}
            </span>
          ) : (
            <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} style={{ justifySelf: 'start' }} onClick={() => setRetried(true)}>
              <RefreshIcon width={15} height={15} />
              {t('app.retry')}
            </button>
          )}
        </div>
      )}

      {a.evaluation_status === 'done' && (
        <>
          <AiNotice method="rules" />
          <p className={ui.body} style={{ margin: '12px 0 16px' }}>
            {a.summary}
          </p>
          <h3 className={ui.sectionTitle}>{t('app.detail.criteria')}</h3>
          <div className={s.evalList} data-active={active !== null || undefined}>
            {criteria.map((c) => {
              const item = a.items.find((i) => i.criterion_id === c.id)!;
              return (
                <div key={c.id} className={s.evalItem} data-lit={active === c.id || undefined}>
                  <div className={s.evalHead}>
                    <span className={s.evalName}>
                      <span className={s.square} data-level={scoreLevel(item.score)} />
                      {c.name}
                    </span>
                    <span className={s.score}>{t('app.detail.score', { n: item.score })}</span>
                  </div>
                  <span className={s.tagRowInline}>
                    <CategoryTag category={c.category} /> <span className={ui.caption} style={{ display: 'inline' }}>{t('app.detail.weight', { n: c.weight })}</span>
                  </span>
                  <p className={ui.body} style={{ fontSize: 13.5 }}>
                    {item.reason}
                  </p>
                  {item.evidence.length > 0 ? (
                    item.evidence.map((q) => (
                      <p key={q} className={ui.quote}>
                        {q}
                      </p>
                    ))
                  ) : (
                    <p className={ui.caption}>{t('app.detail.noEvidence')}</p>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </aside>
  );
}
