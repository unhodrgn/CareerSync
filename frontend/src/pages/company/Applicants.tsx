import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { generatePath, Link, useParams, useSearchParams } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { AiBusy, AiMark } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate } from '@/components/common/format';
import { RefreshIcon } from '@/components/common/icons';
import { ApplicationStatusTag } from '@/components/common/Labels';
import { applicantExperience, GateTag, hasGate } from '@/components/common/RequiredGate';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import ApplicantDetail, { type DetailFocus } from '@/components/company/ApplicantDetail';
import JobHeader from '@/components/company/JobHeader';
import s from '@/components/company/company.module.css';
import CandidateAvatar from '@/components/company/CandidateAvatar';
import h from '@/styles/hiring.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { useDocumentTitle } from '@/routes/title';
import { APPLICATION_STATUSES, type ApplicantList, type ApplicationStatus, type EvaluationStatus } from '@/types/application';
import { GATE_STATUSES, type GateStatusT } from '@/types/gate';

const MIN_FITS = [60, 70, 80];
export function topRankedPair(data: ApplicantList) {
  const first = data.items.find(row => row.rank === 1 && row.evaluation_status === 'done' && row.fit !== null);
  const second = data.items.find(row => row.rank === 2 && row.evaluation_status === 'done' && row.fit !== null);
  return first && second ? [first, second] as const : null;
}

const EVAL_STATUSES: EvaluationStatus[] = ['done', 'pending', 'failed'];
/**
 * Applicants ranked by Fit (D22): the quick filters apply after ranking, so a rank never shifts. The selected
 * applicant (`?selected=`, rank 1 or the first visible one by default) opens beside the table with the evidence
 * first and the status pinned below it; ↑/↓ on a row or the prev/next buttons move the selection, never the ranking.
 */
export default function Applicants() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const job = useApi(() => api.job(id), [id]);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus[]>([]);
  const [minFit, setMinFit] = useState<number | undefined>(undefined);
  const [evalFilter, setEvalFilter] = useState<EvaluationStatus | undefined>(undefined);
  // Required criteria gate (D50): filters the shown list only; it never removes, re-ranks or changes an applicant
  const [gateFilter, setGateFilter] = useState<GateStatusT | undefined>(undefined);
  const list = useApi(
    () => api.applicants(id, { status: statusFilter, min_fit: minFit, evaluation_status: evalFilter, required_gate: gateFilter }),
    [id, statusFilter.join(','), minFit, evalFilter, gateFilter],
  );
  const comparisonList = useApi(() => api.applicants(id), [id]);
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get('selected')) || null;
  const select = (applicationId: number) => setParams({ selected: String(applicationId) }, { replace: true });

  if (job.state.status === 'loading') {
    return (
      <div className={cx(ui.page, h.page)}>
        <Loading rows={8} />
      </div>
    );
  }
  if (job.state.status === 'error') {
    return (
      <div className={cx(ui.page, h.page)}>
        <PageHead title={t('page.company.applicants.title')} back={{ to: paths.company.jobs, label: t('jobTabs.back') }} />
        <ErrorPanel error={job.state.error} onRetry={job.reload} />
      </div>
    );
  }

  // The gate exists only for a job with a minimum experience; otherwise its filter and column stay out
  const gated = (job.state.data.min_experience_years ?? 0) > 0;
  const filtered = statusFilter.length > 0 || minFit !== undefined || evalFilter !== undefined || gateFilter !== undefined;
  return (
    <div className={cx(ui.page, h.page)}>
      <JobHeader job={job.state.data} />
      <div className={s.compareHeading}>
        <h2 className={s.rankingHeading}>{t('jobTabs.applicants')}</h2>
        {comparisonList.state.status === 'ok' && comparisonList.state.data.job_id === id && topRankedPair(comparisonList.state.data) ? (
          <Link className={cx(ui.btn, ui.primary, ui.small)} to={generatePath(paths.company.applicantComparison, { jobId: String(id) })}>
            {t('compare.title')}
          </Link>
        ) : (
          <>
            <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} disabled>{t('compare.title')}</button>
            <span className={ui.caption}>{t(comparisonList.state.status === 'loading' ? 'compare.checking' : comparisonList.state.status === 'error' ? 'compare.unavailable' : 'compare.notEnough')}</span>
            {comparisonList.state.status === 'error' && (
              <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={comparisonList.reload}>{t('common.refresh')}</button>
            )}
          </>
        )}
      </div>
      <div className={cx(ui.panel, s.filters)}>
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
        {gated && (
          <label className={s.filterGroup}>
            {t('gate.filter')}
            <select
              className={cx(ui.select, s.smallSelect)}
              value={gateFilter ?? ''}
              onChange={(e) => setGateFilter((e.target.value || undefined) as GateStatusT | undefined)}
            >
              <option value="">{t('apl.filter.all')}</option>
              {GATE_STATUSES.map((x) => (
                <option key={x} value={x}>
                  {t(`gate.status.${x}`)}
                </option>
              ))}
            </select>
          </label>
        )}
        {filtered && (
          <button
            type="button"
            className={cx(ui.btn, ui.quiet, ui.small)}
            onClick={() => (setStatusFilter([]), setMinFit(undefined), setEvalFilter(undefined), setGateFilter(undefined))}
          >
            {t('apl.filter.reset')}
          </button>
        )}
      </div>

      {list.state.status === 'loading' && <Loading rows={6} />}
      {list.state.status === 'error' && <ErrorPanel error={list.state.error} onRetry={list.reload} />}
      {list.state.status === 'ok' && (
        <Board
          data={list.state.data}
          selected={selected}
          onSelect={select}
          onRefresh={() => { list.reload(); comparisonList.reload(); }}
          setData={list.setData}
          filtered={filtered}
          gated={gated}
          gateFiltered={gateFilter !== undefined}
        />
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
  gated,
  gateFiltered,
}: {
  data: ApplicantList;
  selected: number | null;
  onSelect: (id: number) => void;
  onRefresh: () => void;
  setData: (d: ApplicantList) => void;
  filtered: boolean;
  /** The job sets a minimum experience: the gate column shows (D50). */
  gated: boolean;
  gateFiltered: boolean;
}) {
  const items = data.items;
  const index = items.findIndex((r) => r.application_id === selected);
  const current = index >= 0 ? items[index] : null;
  // The open applicant names the tab (홍길동 – 지원자 상세 – CareerSync); none open keeps 지원자 관리
  useDocumentTitle(current?.name, 'page.company.applicantDetail.title');
  const rowRefs = useRef(new Map<number, HTMLTableRowElement>());
  const requests = useRef(0);
  const [focusRequest, setFocusRequest] = useState<(DetailFocus & { id: number }) | null>(null);
  const [announce, setAnnounce] = useState('');

  // Rank 1, or the first visible applicant when filtered, opens by default; focus stays where it is
  const firstId = items[0]?.application_id;
  useEffect(() => {
    if (index < 0 && firstId !== undefined) onSelect(firstId);
  }, [index, firstId, onSelect]);

  if (data.total_count === 0) return <Empty title={t('apl.empty.title')} body={t('apl.empty.body')} />;

  // Moving through the list only changes the selection; the ranking and its order stay as computed
  const openRow = (applicationId: number) => {
    onSelect(applicationId);
    setFocusRequest({ id: applicationId, target: 'heading', n: ++requests.current });
  };
  const step = (to: number, target: 'prev' | 'next') => {
    const r = items[to];
    if (!r) return;
    onSelect(r.application_id);
    setFocusRequest({ id: r.application_id, target, n: ++requests.current });
    setAnnounce(t('apl.nav.announce', { position: to + 1, name: r.name }));
    rowRefs.current.get(r.application_id)?.scrollIntoView({ block: 'nearest' });
  };
  const onKey = (e: KeyboardEvent, i: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openRow(items[i].application_id);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const next = items[i + (e.key === 'ArrowDown' ? 1 : -1)];
      if (!next) return;
      e.preventDefault();
      onSelect(next.application_id);
      rowRefs.current.get(next.application_id)?.focus();
    }
  };
  const rowLabel = (a: (typeof items)[number], isSelected: boolean) => {
    const who = a.rank ? t('apl.row.ranked', { rank: a.rank, name: a.name }) : a.name;
    return isSelected ? t('apl.row.selected', { label: who }) : who;
  };
  const pending = data.items.some((r) => r.evaluation_status === 'pending');
  const facts = (a: (typeof items)[number]) =>
    // The gate's stated total replaces a period-based 0 that would contradict it (D50); otherwise as before
    a.evaluation_status === 'done' ? applicantExperience(a.experience_months, a.required_gate) : null;

  return (
    <div className={s.board}>
      <section className={cx(ui.panel, s.rankingPanel)} aria-labelledby="ranking-title">
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
        {gateFiltered && <p className={ui.caption}>{t('gate.filter.note')}</p>}
        {data.items.length === 0 ? (
          <Empty panel={false} title={t('apl.noMatch')} />
        ) : (
          <div className={s.rankingScroll} role="region" aria-labelledby="ranking-title">
            <table className={cx(ui.table, s.ranking)} role="table" aria-labelledby="ranking-title">
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">{t('apl.col.rank')}</th>
                  <th role="columnheader" scope="col">{t('apl.col.name')}</th>
                  <th role="columnheader" scope="col">{t('apl.col.status')}</th>
                  <th role="columnheader" scope="col">{t('apl.col.date')}</th>
                  <th role="columnheader" scope="col">
                    <span className={s.aiHead}><AiMark size="sm" />{t('apl.col.fit')}</span>
                  </th>
                  {gated && <th role="columnheader" scope="col">{t('gate.col')}</th>}
                  <th role="columnheader" scope="col"><span className={ui.visuallyHidden}>{t('jobs.details')}</span></th>
                </tr>
              </thead>
              <tbody className={ui.stagger} role="rowgroup">
                {items.map((a, i) => (
                  <tr
                    role="row"
                    key={a.application_id}
                    ref={(el) => {
                      if (el) rowRefs.current.set(a.application_id, el);
                      else rowRefs.current.delete(a.application_id);
                    }}
                    className={s.applicantRow}
                    tabIndex={0}
                    // A focused row is read by its name, and Chromium gives a table row none from its cells; aria-selected
                    // is for grids. So the row is named — rank and applicant, 선택됨 first when selected — and the table
                    // keeps its native semantics; data-selected only draws the selection
                    aria-label={rowLabel(a, selected === a.application_id)}
                    data-selected={selected === a.application_id || undefined}
                    onClick={() => openRow(a.application_id)}
                    onKeyDown={(e) => onKey(e, i)}
                  >
                    <td role="cell" className={s.rankCell}>{a.rank ? <span className={s.rank} data-top={a.rank === 1 || undefined}>{a.rank}</span> : <span className={ui.muted}>—</span>}</td>
                    <td role="cell" className={s.personCell}>
                      <span className={s.person}>
                        {/* Seeded by the application, never by the name or email; kept apart from the talent seed */}
                        <CandidateAvatar seed={`A-${a.application_id}`} />
                        <span className={s.nameCell}>
                          <strong title={a.name}>{a.name}</strong>
                          {facts(a) && <span className={ui.caption}>{facts(a)}</span>}
                        </span>
                      </span>
                    </td>
                    <td role="cell"><ApplicationStatusTag status={a.status} /></td>
                    <td role="cell" className={cx(ui.num, s.dateCell)}>
                      <span className={s.mobileLabel}>{t('apl.col.date')}</span>
                      {a.applied_at ? formatDate(a.applied_at) : '—'}
                    </td>
                    <td role="cell" className={s.fitCell}>
                      {a.fit !== null ? (
                        <span className={s.fitRing} style={{ background: `conic-gradient(#147a73 ${a.fit}%, #e4edf0 0)` }}><span>{a.fit.toFixed(1)}</span></span>
                      ) : a.evaluation_status === 'pending' ? (
                        <AiBusy as="span">{t('evalStatus.pending')}</AiBusy>
                      ) : (
                        <span className={ui.caption}>{t(`evalStatus.${a.evaluation_status}`)}</span>
                      )}
                    </td>
                    {gated && (
                      <td role="cell" className={s.gateCell}>
                        <span className={s.mobileLabel}>{t('gate.col')}</span>
                        {hasGate(a.required_gate) ? <GateTag status={a.required_gate.status} short /> : <span className={ui.muted}>—</span>}
                      </td>
                    )}
                    <td role="cell" className={s.openCell}>
                      <button
                        type="button"
                        className={cx(ui.btn, ui.primary, ui.small)}
                        aria-label={t('apl.openFor', { name: a.name })}
                        onClick={(event) => {
                          event.stopPropagation();
                          openRow(a.application_id);
                        }}
                        onKeyDown={(event) => event.stopPropagation()}
                      >
                        {t('apl.open')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
          jobId={data.job_id}
          criteriaCount={data.criteria.length}
          position={index + 1}
          total={items.length}
          onPrev={index > 0 ? () => step(index - 1, 'prev') : undefined}
          onNext={index < items.length - 1 ? () => step(index + 1, 'next') : undefined}
          focusRequest={focusRequest?.id === current.application_id ? focusRequest : null}
          onEscape={() => rowRefs.current.get(current.application_id)?.focus()}
          onStatusChanged={(status) => setData({ ...data, items: data.items.map((r) => (r.application_id === current.application_id ? { ...r, status } : r)) })}
          onEvaluationChanged={onRefresh}
        />
      ) : (
        <aside className={cx(ui.panel, s.detailPlaceholder)}>
          <p className={ui.caption}>{t('apl.select')}</p>
        </aside>
      )}
      {/* Says who opened after the prev/next buttons; a focused row is read out by itself */}
      <p className={ui.visuallyHidden} role="status">
        {announce}
      </p>
    </div>
  );
}
