import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { AiBusy, AiMark } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate } from '@/components/common/format';
import { RefreshIcon } from '@/components/common/icons';
import { ApplicationStatusTag, ScoreSquare } from '@/components/common/Labels';
import { applicantExperience, GateTag, hasGate } from '@/components/common/RequiredGate';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import ApplicantDetail, { type DetailFocus } from '@/components/company/ApplicantDetail';
import JobHeader from '@/components/company/JobHeader';
import s from '@/components/company/company.module.css';
import CandidateAvatar from '@/components/company/CandidateAvatar';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { useDocumentTitle } from '@/routes/title';
import { APPLICATION_STATUSES, type ApplicantList, type ApplicationStatus, type EvaluationStatus } from '@/types/application';
import { GATE_STATUSES, type GateStatusT } from '@/types/gate';

const MIN_FITS = [60, 70, 80];
const EVAL_STATUSES: EvaluationStatus[] = ['done', 'pending', 'failed'];
// Criteria columns: equal shares of what is left after rank (40) + Fit (72) + the applicant (at least 168) + the
// minimum-experience gate (88, only when the job sets a minimum), kept between 40 and 96 px; under 80 px a name no
// longer fits on two horizontal lines, so the headers turn 45°. The fixed widths live in company.module.css
// (.colRank, .colFit, .colGate).
const RESERVED = 40 + 72 + 168;
const GATE_COLUMN = 88;
const MIN_COLUMN = 40;
const MAX_COLUMN = 96;
const COMFORTABLE_COLUMN = 80;

/**
 * Sets each criterion column's width (--crit-w, plain px: Chrome treats percentage calc() widths on table columns
 * as auto) from the table's width, and says whether the headers are angled. The table is width: 100% with a fixed
 * layout, so its width never depends on these columns or the header height, and measuring again cannot loop.
 */
function useCriteriaColumns(ref: RefObject<HTMLTableElement | null>, count: number, active: boolean, reserved = RESERVED) {
  const [dense, setDense] = useState(false);
  useLayoutEffect(() => {
    const table = ref.current;
    if (!active || !table || count === 0) return;
    const fit = () => {
      const share = Math.floor(((table.clientWidth - reserved) / count) * 10) / 10;
      const width = Math.min(MAX_COLUMN, Math.max(MIN_COLUMN, share));
      table.style.setProperty('--crit-w', `${width}px`);
      setDense(width < COMFORTABLE_COLUMN);
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(table);
    return () => observer.disconnect();
  }, [ref, count, active, reserved]);
  return dense;
}

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

  // The gate exists only for a job with a minimum experience; otherwise its filter and column stay out
  const gated = (job.state.data.min_experience_years ?? 0) > 0;
  const filtered = statusFilter.length > 0 || minFit !== undefined || evalFilter !== undefined || gateFilter !== undefined;
  return (
    <div className={ui.page}>
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
          onRefresh={list.reload}
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
  const tableRef = useRef<HTMLTableElement>(null);
  const dense = useCriteriaColumns(tableRef, data.criteria.length, items.length > 0, RESERVED + (gated ? GATE_COLUMN : 0));
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
    a.evaluation_status === 'done' ? applicantExperience(a.experience_months, a.required_gate) : t('apl.applied', { date: formatDate(a.applied_at) });

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
        {gateFiltered && <p className={ui.caption}>{t('gate.filter.note')}</p>}
        {data.items.length === 0 ? (
          <Empty panel={false} title={t('apl.noMatch')} />
        ) : (
          <table
            ref={tableRef}
            className={cx(ui.table, s.ranking)}
            style={{ marginTop: 12 }}
            data-dense={dense || undefined}
          >
            <colgroup>
              <col className={s.colRank} />
              <col />
              <col className={s.colFit} />
              {data.criteria.map((c) => (
                <col key={c.id} className={s.colCrit} />
              ))}
              {gated && <col className={s.colGate} />}
            </colgroup>
            <thead>
              <tr>
                <th>{t('apl.col.rank')}</th>
                <th>{t('apl.col.name')}</th>
                {/* Fit sits by the name: rank, applicant and fit read as one; the criteria after it are the evidence */}
                <th className={s.fitHead}>
                  <span className={s.aiHead}>
                    <AiMark size="sm" />
                    {t('apl.col.fit')}
                  </span>
                </th>
                {/* The name may be cut short on screen; the title and the label keep it whole */}
                {data.criteria.map((c) => (
                  <th
                    key={c.id}
                    data-crit
                    className={s.critHead}
                    title={c.name}
                    aria-label={`${c.name}, ${t('apl.detail.weight', { n: Math.round(c.weight) })}`}
                  >
                    <span className={s.critHeadName}>{c.name}</span>
                    <span className={s.critHeadWeight}>{Math.round(c.weight)}%</span>
                  </th>
                ))}
                {/* After the criteria, apart from Fit and its evidence: a label about the job's minimum, not a score */}
                {gated && <th className={s.gateHead}>{t('gate.col')}</th>}
              </tr>
            </thead>
            <tbody className={ui.stagger}>
              {items.map((a, i) => (
                <tr
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
                  onClick={() => onSelect(a.application_id)}
                  onKeyDown={(e) => onKey(e, i)}
                >
                  <td>{a.rank ? <span className={s.rank} data-top={a.rank === 1 || undefined}>{a.rank}</span> : <span className={ui.muted}>—</span>}</td>
                  <td>
                    <span className={s.person}>
                      {/* Seeded by the application, never by the name or email; kept apart from the talent seed */}
                      <CandidateAvatar seed={`A-${a.application_id}`} />
                      <span className={s.nameCell}>
                        <strong title={a.name}>{a.name}</strong>
                        {/* Status and experience stay whole: side by side when there is room, on two lines when not */}
                        <span className={cx(ui.caption, s.nameFacts)}>
                          <ApplicationStatusTag status={a.status} />
                          <span>{facts(a)}</span>
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className={s.fitCell}>
                    {a.fit !== null ? (
                      <span className={s.fit}>{a.fit.toFixed(1)}</span>
                    ) : a.evaluation_status === 'pending' ? (
                      <AiBusy as="span">{t('evalStatus.pending')}</AiBusy>
                    ) : (
                      <span className={ui.caption}>{t(`evalStatus.${a.evaluation_status}`)}</span>
                    )}
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
                  {gated && (
                    <td className={s.gateCell}>
                      {hasGate(a.required_gate) ? <GateTag status={a.required_gate.status} short /> : <span className={ui.muted}>—</span>}
                    </td>
                  )}
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
