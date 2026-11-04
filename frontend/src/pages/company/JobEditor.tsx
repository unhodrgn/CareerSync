import { useEffect, useRef, useState, type ReactNode } from 'react';
import { generatePath, Link, useLocation, useNavigate, useParams } from 'react-router';
import { ApiError, api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { AlertIcon, CheckIcon, PlusIcon, TrashIcon } from '@/components/common/icons';
import { CategoryTag, ImportanceTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import CriteriaSuggestions from '@/components/company/CriteriaSuggestions';
import JdDraftPanel from '@/components/company/JdDraftPanel';
import JobHeader from '@/components/company/JobHeader';
import s from '@/components/company/company.module.css';
import { t, type MessageKey } from '@/i18n';
import { paths } from '@/routes/paths';
import { CATEGORIES, type Category, type CriteriaSetOut, type GuardrailHit, type Importance } from '@/types/criteria';
import { EMPLOYMENT_TYPES, type EmploymentType, type JdAnalysisOut, type JobCreate, type JobOut } from '@/types/job';

const MAX_CRITERIA = 10;
const WEIGHT_TOTAL = 100;
// After publish only these job fields may change (backend EDITABLE_AFTER_PUBLISH)
const EDITABLE_AFTER_PUBLISH: (keyof JobCreate)[] = ['deadline', 'location', 'salary_note'];

interface Form {
  title: string;
  employment_type: EmploymentType;
  min_experience_years: string;
  location: string;
  salary_note: string;
  deadline: string;
  description: string;
}

interface Row {
  key: number;
  id?: number;
  name: string;
  description: string;
  category: Category;
  weight: string;
}

/** What the new-job page hands to the edit page after creating the job (the route changes, the page remounts). */
interface Handoff {
  rows?: Row[];
  criteriaError?: unknown;
  saved?: boolean;
  /** What the recruiter asked for on the new-job page, to finish once the job exists. */
  then?: 'draft' | 'analyze' | 'publish';
}

let nextKey = 1;
const blankForm: Form = { title: '', employment_type: 'full_time', min_experience_years: '', location: '', salary_note: '', deadline: '', description: '' };

const formOf = (job: JobOut): Form => ({
  title: job.title,
  employment_type: job.employment_type,
  min_experience_years: job.min_experience_years == null ? '' : String(job.min_experience_years),
  location: job.location,
  salary_note: job.salary_note,
  deadline: job.deadline ?? '',
  description: job.description,
});

const rowsOf = (set: CriteriaSetOut): Row[] =>
  set.items.map((c) => ({ key: nextKey++, id: c.id, name: c.name, description: c.description, category: c.category, weight: String(c.weight) }));

const bodyOf = (f: Form): JobCreate => ({
  title: f.title.trim(),
  description: f.description,
  employment_type: f.employment_type,
  min_experience_years: f.min_experience_years === '' ? null : Number(f.min_experience_years),
  location: f.location.trim(),
  salary_note: f.salary_note.trim(),
  deadline: f.deadline || null,
});

const sameRows = (a: Row[], b: Row[]) =>
  JSON.stringify(a.map(({ key: _k, ...r }) => r)) === JSON.stringify(b.map(({ key: _k, ...r }) => r));

/** Job editor for /company/jobs/new and /company/jobs/:jobId/edit; remounts per job. */
export default function JobEditor() {
  const { jobId } = useParams();
  return <Loader key={jobId ?? 'new'} jobId={jobId ? Number(jobId) : null} />;
}

function Loader({ jobId }: { jobId: number | null }) {
  const [state, setState] = useState<{ job: JobOut; criteria: CriteriaSetOut } | 'new' | 'loading' | { error: unknown }>(
    jobId == null ? 'new' : 'loading',
  );
  const [round, setRound] = useState(0);
  useEffect(() => {
    if (jobId == null) return;
    let current = true;
    setState('loading');
    Promise.all([api.job(jobId), api.ownCriteria(jobId)]).then(
      ([job, criteria]) => current && setState({ job, criteria }),
      (error: unknown) => current && setState({ error }),
    );
    return () => {
      current = false;
    };
  }, [jobId, round]);

  if (state === 'loading') {
    return (
      <div className={ui.page}>
        <Loading rows={8} />
      </div>
    );
  }
  if (typeof state === 'object' && 'error' in state) {
    return (
      <div className={ui.page}>
        <PageHead title={t('page.company.jobEditor.title')} back={{ to: paths.company.jobs, label: t('jobTabs.back') }} />
        <ErrorPanel error={state.error} onRetry={() => setRound((r) => r + 1)} />
      </div>
    );
  }
  return <Editor initial={state === 'new' ? null : state} />;
}

function Editor({ initial }: { initial: { job: JobOut; criteria: CriteriaSetOut } | null }) {
  const navigate = useNavigate();
  const location = useLocation();
  const handoff = (location.state as { handoff?: Handoff } | null)?.handoff;

  const [job, setJob] = useState<JobOut | null>(initial?.job ?? null);
  const [savedForm, setSavedForm] = useState<Form>(initial ? formOf(initial.job) : blankForm);
  const [form, setForm] = useState<Form>(savedForm);
  const [savedCriteria, setSavedCriteria] = useState<CriteriaSetOut | null>(initial?.criteria ?? null);
  const [savedRows, setSavedRows] = useState<Row[]>(() => (initial ? rowsOf(initial.criteria) : []));
  const [rows, setRows] = useState<Row[]>(() => handoff?.rows ?? savedRows);

  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [hits, setHits] = useState<Record<number, GuardrailHit[]>>({});
  const [totalError, setTotalError] = useState(false);
  const [pageError, setPageError] = useState<unknown>(handoff?.criteriaError ?? null);
  const [notice, setNotice] = useState<MessageKey | null>(handoff?.saved ? 'editor.saved' : null);
  const [busy, setBusy] = useState<'save' | 'publish' | 'close' | 'delete' | 'analyze' | null>(null);
  const [confirm, setConfirm] = useState<'close' | 'delete' | null>(null);
  const [draftOpen, setDraftOpen] = useState(handoff?.then === 'draft');
  const [analysis, setAnalysis] = useState<JdAnalysisOut | null>(null);
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement, HTMLParagraphElement>(confirm !== null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  // The latest rows, for answers that arrive after the user typed on (live guardrail check)
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const status = job?.status ?? 'draft';
  const closed = status === 'closed';
  const published = status === 'published';
  // Basics, JD and criteria content are fixed once applicants are scored against them
  const basicsLocked = published || closed;
  const dirty = JSON.stringify(form) !== JSON.stringify(savedForm) || !sameRows(rows, savedRows);
  const total = rows.reduce((sum, r) => sum + (Number(r.weight) || 0), 0);

  const setField = <K extends keyof Form>(k: K, v: Form[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setFieldErrors((e) => ({ ...e, [k]: undefined }));
    setNotice(null);
  };
  const updateRow = (key: number, patch: Partial<Row>) => {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
    setRowErrors((e) => ({ ...e, [key]: '' }));
    if ('name' in patch || 'description' in patch) setHits((h) => ({ ...h, [key]: [] }));
    setTotalError(false);
    setNotice(null);
  };
  const addRow = (r?: Partial<Row>) => {
    if (rows.length >= MAX_CRITERIA) return;
    setRows((rs) => [...rs, { key: nextKey++, name: '', description: '', category: 'skill', weight: '', ...r }]);
    setNotice(null);
  };
  const removeRow = (key: number) => (setRows((rs) => rs.filter((r) => r.key !== key)), setNotice(null));

  // Live legal-guardrail check when a criterion's field loses focus (saves nothing; the save checks again)
  const checkRow = async (row: Row) => {
    if (!row.name.trim() || basicsLocked) return;
    try {
      const res = await api.checkCriterion(row.name.trim(), row.description.trim());
      const now = rowsRef.current.find((r) => r.key === row.key);
      // Typed on meanwhile: this answer is for older text
      if (now && now.name === row.name && now.description === row.description) setHits((h) => ({ ...h, [row.key]: res.hits }));
    } catch {
      // The save checks again; a failed live check is not worth an error here
    }
  };

  /** Client checks that mirror PUT /criteria, so most errors show before the request. */
  const validateRows = (): boolean => {
    if (rows.length === 0) return true;
    const errs: Record<number, string> = {};
    for (const r of rows) {
      const w = Number(r.weight);
      if (!r.name.trim()) errs[r.key] = t('editor.nameRequired');
      else if (!Number.isInteger(w) || w < 1 || w > 100) errs[r.key] = t('editor.weightRange');
    }
    setRowErrors(errs);
    const totalOff = total !== WEIGHT_TOTAL;
    setTotalError(totalOff);
    return Object.keys(errs).length === 0 && !totalOff;
  };

  /** Server errors spread over the form: fields, criterion rows, the total, or the page. */
  const showError = (e: unknown) => {
    const code = errorCode(e);
    const body = e instanceof ApiError ? e.body : null;
    const byIndex = (index: number) => rows[index]?.key;
    if (code === 'CRITERIA_BLOCKED' && Array.isArray(body?.items)) {
      const next: Record<number, GuardrailHit[]> = {};
      for (const hit of body.items as GuardrailHit[]) {
        const key = hit.index == null ? undefined : byIndex(hit.index);
        if (key !== undefined) next[key] = [...(next[key] ?? []), hit];
      }
      setHits(next);
    } else if (code === 'CRITERIA_MAJOR_REQUIRED' && Array.isArray(body?.items)) {
      const errs: Record<number, string> = {};
      for (const item of body.items as { index: number }[]) {
        const key = byIndex(item.index);
        if (key !== undefined) errs[key] = t('editor.majorRequired');
      }
      setRowErrors(errs);
    } else if (code === 'CRITERIA_DUPLICATE_NAME' && Array.isArray(body?.names)) {
      const names = (body.names as string[]).map((n) => n.toLowerCase());
      const errs: Record<number, string> = {};
      for (const r of rows) if (names.includes(r.name.trim().toLowerCase())) errs[r.key] = t('error.criteriaDuplicate');
      setRowErrors(errs);
    } else if (code === 'WEIGHT_SUM_INVALID') {
      setTotalError(true);
    } else if (code === 'DEADLINE_IN_PAST') {
      setFieldErrors({ deadline: errorText(e) });
      return;
    } else if (code === 'JOB_INCOMPLETE') {
      setFieldErrors({ description: errorText(e) });
      descriptionRef.current?.focus();
      return;
    } else if (code === 'VALIDATION' && e instanceof ApiError) {
      const errs: Partial<Record<keyof Form, string>> = {};
      for (const name of Object.keys(e.fields)) if (name in blankForm) errs[name as keyof Form] = t('error.validation');
      setFieldErrors(errs);
    }
    setPageError(e);
  };

  /**
   * Create or update the job and its criteria; resolves to the saved job, or null when something failed. A new job
   * moves to its own edit page (`then` says what to finish there).
   */
  const save = async (then?: Handoff['then']): Promise<JobOut | null> => {
    setPageError(null);
    setNotice(null);
    if (!job && !form.title.trim()) {
      setFieldErrors({ title: t('editor.titleRequired') });
      return null;
    }
    if (!sameRows(rows, savedRows) && !validateRows()) return null;

    let current = job;
    try {
      if (!current) {
        current = await api.createJob(bodyOf(form));
      } else if (JSON.stringify(form) !== JSON.stringify(savedForm)) {
        const body = bodyOf(form);
        const before = bodyOf(savedForm);
        const fields = (published ? EDITABLE_AFTER_PUBLISH : (Object.keys(body) as (keyof JobCreate)[])).filter(
          (k) => body[k] !== before[k],
        );
        if (fields.length) current = await api.updateJob(current.id, Object.fromEntries(fields.map((k) => [k, body[k]])));
      }
    } catch (e) {
      showError(e);
      return null;
    }

    // A new job gets its own page; the criteria (and any error with them) travel along
    if (!job) {
      const handoffRows = rows.length ? rows : undefined;
      let criteriaError: unknown = null;
      if (rows.length) {
        try {
          await api.saveCriteria(current.id, rows.map((r) => ({ name: r.name.trim(), description: r.description.trim(), category: r.category, weight: Number(r.weight) })));
        } catch (e) {
          criteriaError = e;
        }
      }
      navigate(generatePath(paths.company.jobEdit, { jobId: String(current.id) }), {
        replace: true,
        state: {
          handoff: { rows: criteriaError ? handoffRows : undefined, criteriaError, saved: !criteriaError, then: criteriaError ? undefined : then } satisfies Handoff,
        },
      });
      return null;
    }

    if (!sameRows(rows, savedRows) && rows.length) {
      try {
        const set = await api.saveCriteria(
          current.id,
          rows.map((r) => ({
            ...(published && r.id ? { id: r.id } : {}),
            name: r.name.trim(),
            description: r.description.trim(),
            category: r.category,
            weight: Number(r.weight),
          })),
        );
        const fresh = rowsOf(set);
        setSavedCriteria(set);
        setSavedRows(fresh);
        setRows(fresh);
        setHits({});
      } catch (e) {
        setJob(current);
        setSavedForm(form);
        showError(e);
        return null;
      }
    }
    setJob(current);
    setSavedForm(formOf(current));
    setForm(formOf(current));
    return current;
  };

  const run = async (kind: 'save' | 'publish' | 'close' | 'delete', action: () => Promise<void>) => {
    setBusy(kind);
    try {
      await action();
    } finally {
      setBusy(null);
    }
  };

  const onSave = () =>
    run('save', async () => {
      if (await save()) setNotice('editor.saved');
    });

  const onPublish = () =>
    run('publish', async () => {
      const current = dirty || !job ? await save('publish') : job;
      if (!current) return;
      try {
        setJob(await api.publishJob(current.id));
        setNotice('editor.published');
      } catch (e) {
        showError(e);
      }
    });

  const onClose = () =>
    run('close', async () => {
      if (!job) return;
      try {
        const closedJob = await api.closeJob(job.id);
        setJob(closedJob);
        setSavedForm(formOf(closedJob));
        setForm(formOf(closedJob));
        setRows(savedRows);
        setConfirm(null);
        setNotice('editor.closedDone');
      } catch (e) {
        setConfirm(null);
        showError(e);
      }
    });

  const onDelete = () =>
    run('delete', async () => {
      if (!job) return;
      try {
        await api.deleteJob(job.id);
        navigate(paths.company.jobs, { replace: true });
      } catch (e) {
        setConfirm(null);
        showError(e);
      }
    });

  // AI draft and suggestions read the saved job: a new or changed job is saved first
  const ensureSaved = async (then: 'draft' | 'analyze'): Promise<JobOut | null> => {
    if (!job) {
      if (!form.title.trim()) {
        setFieldErrors({ title: t('editor.titleRequired') });
        return null;
      }
      setBusy('save');
      try {
        const created = await api.createJob(bodyOf(form));
        navigate(generatePath(paths.company.jobEdit, { jobId: String(created.id) }), {
          replace: true,
          state: { handoff: { rows: rows.length ? rows : undefined, then } satisfies Handoff },
        });
      } catch (e) {
        showError(e);
      } finally {
        setBusy(null);
      }
      return null;
    }
    return dirty ? save() : job;
  };

  const onAnalyze = async () => {
    setBusy('analyze');
    setPageError(null);
    try {
      const current = await ensureSaved('analyze');
      if (current) setAnalysis(await api.analyzeJob(current.id));
    } catch (e) {
      setPageError(e);
    } finally {
      setBusy(null);
    }
  };

  // Arrived from the new-job page: show what failed there, or finish the step that needed a saved job. The state is
  // consumed once, so a reload does not repeat it.
  const handoffRun = useRef(false);
  useEffect(() => {
    if (handoffRun.current || !handoff) return;
    handoffRun.current = true;
    navigate(location.pathname, { replace: true, state: null });
    if (handoff.criteriaError) showError(handoff.criteriaError);
    else if (handoff.then === 'analyze') void onAnalyze();
    else if (handoff.then === 'publish') void onPublish();
  }, []);

  const importanceByName = new Map<string, Importance>((savedCriteria?.items ?? []).map((c) => [`${c.name}|${c.weight}`, c.importance]));

  return (
    <div className={ui.page}>
      {job ? <JobHeader job={job} /> : <PageHead title={t('editor.newTitle')} back={{ to: paths.company.jobs, label: t('jobTabs.back') }} />}

      <div className={s.editor}>
        <div className={ui.stack}>
          {basicsLocked && (
            // After 마감 the confirm's trigger is gone: focus lands here
            <p ref={focus.fallbackRef} tabIndex={-1} className={ui.notice}>
              {closed ? t('editor.closed') : t('editor.lockedHint')}
            </p>
          )}

          <section className={ui.panel} aria-labelledby="basics-title">
            <h2 id="basics-title" className={ui.panelTitle} style={{ marginBottom: 16 }}>
              {t('editor.basics')}
            </h2>
            <div className={s.grid3}>
              <Field label={t('editor.titleLabel')} error={fieldErrors.title} className={s.span2}>
                <input
                  className={ui.input}
                  value={form.title}
                  maxLength={200}
                  readOnly={basicsLocked}
                  placeholder={t('editor.titlePlaceholder')}
                  aria-invalid={fieldErrors.title ? true : undefined}
                  onChange={(e) => setField('title', e.target.value)}
                />
              </Field>
              <Field label={t('editor.employment')}>
                <select
                  className={ui.select}
                  value={form.employment_type}
                  disabled={basicsLocked}
                  onChange={(e) => setField('employment_type', e.target.value as EmploymentType)}
                >
                  {EMPLOYMENT_TYPES.map((x) => (
                    <option key={x} value={x}>
                      {t(`employment.${x}`)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('editor.minExperience')} hint={t('editor.minExperienceHint')} error={fieldErrors.min_experience_years}>
                <input
                  className={ui.input}
                  type="number"
                  min={0}
                  max={30}
                  value={form.min_experience_years}
                  readOnly={basicsLocked}
                  onChange={(e) => setField('min_experience_years', e.target.value)}
                />
              </Field>
              <Field label={t('editor.location')} error={fieldErrors.location}>
                <input className={ui.input} value={form.location} maxLength={100} readOnly={closed} onChange={(e) => setField('location', e.target.value)} />
              </Field>
              <Field label={t('editor.deadline')} hint={t('editor.deadlineHint')} error={fieldErrors.deadline}>
                <input
                  className={ui.input}
                  type="date"
                  value={form.deadline}
                  readOnly={closed}
                  aria-invalid={fieldErrors.deadline ? true : undefined}
                  onChange={(e) => setField('deadline', e.target.value)}
                />
              </Field>
              <Field label={t('editor.salary')} hint={t('editor.salaryHint')} error={fieldErrors.salary_note} className={s.span2}>
                <input className={ui.input} value={form.salary_note} maxLength={100} readOnly={closed} onChange={(e) => setField('salary_note', e.target.value)} />
              </Field>
            </div>
          </section>

          <section className={ui.panel} aria-labelledby="jd-title">
            <div className={s.sectionHead}>
              <h2 id="jd-title" className={ui.panelTitle}>
                {t('editor.jd')}
              </h2>
              {!basicsLocked && !draftOpen && (
                <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} disabled={busy !== null} onClick={async () => (job ? setDraftOpen(true) : ensureSaved('draft'))}>
                  {t('editor.aiDraft')}
                </button>
              )}
            </div>
            <Field label={t('editor.jd')} hideLabel error={fieldErrors.description}>
              <textarea
                ref={descriptionRef}
                className={ui.textarea}
                rows={11}
                maxLength={10000}
                value={form.description}
                readOnly={basicsLocked}
                placeholder={t('editor.jdPlaceholder')}
                aria-invalid={fieldErrors.description ? true : undefined}
                onChange={(e) => setField('description', e.target.value)}
              />
            </Field>
            {draftOpen && job && !basicsLocked && (
              <JdDraftPanel
                jobId={job.id}
                onClose={() => setDraftOpen(false)}
                onApply={(text) => {
                  setField('description', text);
                  setDraftOpen(false);
                  setNotice('editor.draft.applied');
                  descriptionRef.current?.focus();
                }}
              />
            )}
          </section>

          <section className={ui.panel} aria-labelledby="criteria-title">
            <div className={s.sectionHead}>
              <div>
                <h2 id="criteria-title" className={ui.panelTitle}>
                  {t('editor.criteria')}
                  <span className={ui.count}>
                    {rows.length}/{MAX_CRITERIA}
                  </span>
                </h2>
                <p className={ui.caption} style={{ marginTop: 4 }}>
                  {t('editor.criteriaLead')}
                </p>
              </div>
              {!basicsLocked && !analysis && (
                <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} disabled={busy !== null} onClick={onAnalyze}>
                  {busy === 'analyze' ? t('editor.suggest.running') : t('editor.suggest')}
                </button>
              )}
            </div>

            {rows.length === 0 ? (
              <p className={ui.caption}>{t('editor.criteriaEmpty')}</p>
            ) : (
              <ul className={s.critList}>
                {rows.map((r, i) => (
                  <CriterionRow
                    key={r.key}
                    index={i}
                    row={r}
                    locked={basicsLocked}
                    weightLocked={closed}
                    error={rowErrors[r.key]}
                    hits={hits[r.key] ?? []}
                    onChange={(patch) => updateRow(r.key, patch)}
                    onBlurCheck={() => checkRow(r)}
                    onRemove={() => removeRow(r.key)}
                  />
                ))}
              </ul>
            )}

            <div className={s.critFoot}>
              {basicsLocked ? (
                <span />
              ) : (
                <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => addRow()} disabled={rows.length >= MAX_CRITERIA}>
                  <PlusIcon width={15} height={15} />
                  {t('editor.criterion.add')}
                </button>
              )}
              <span className={s.total}>
                {t('editor.total')}
                <span className={s.totalValue} data-off={rows.length > 0 && total !== WEIGHT_TOTAL ? true : undefined}>
                  {total} / {WEIGHT_TOTAL}
                </span>
              </span>
            </div>
            {totalError && (
              <div style={{ marginTop: 10 }}>
                <InlineError>{t('editor.totalError', { n: total })}</InlineError>
              </div>
            )}

            {analysis && (
              <CriteriaSuggestions
                result={analysis}
                existing={rows.map((r) => r.name)}
                full={rows.length >= MAX_CRITERIA}
                onClose={() => setAnalysis(null)}
                onAdd={(c) => addRow({ name: c.name, description: c.description, category: c.category, weight: String(c.weight) })}
              />
            )}
          </section>

          {pageError != null && <InlineError>{errorText(pageError)}</InlineError>}

          {!closed && (
            <div className={ui.actionBar}>
              {confirm ? (
                <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t(confirm === 'close' ? 'editor.closeTitle' : 'editor.deleteTitle')} className={s.confirmBar}>
                  <span className={ui.actionBarText}>
                    <strong>{t(confirm === 'close' ? 'editor.closeTitle' : 'editor.deleteTitle')}</strong> {t(confirm === 'close' ? 'editor.closeBody' : 'editor.deleteBody')}
                  </span>
                  <button type="button" className={cx(ui.btn, ui.secondary)} disabled={busy !== null} onClick={confirm === 'close' ? onClose : onDelete}>
                    {t(confirm === 'close' ? 'editor.close' : 'editor.deleteConfirm')}
                  </button>
                  <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy !== null} onClick={() => setConfirm(null)}>
                    {t('common.cancel')}
                  </button>
                </div>
              ) : (
                <>
                  <span className={ui.actionBarText} role="status">
                    {notice ? (
                      <span className={ui.done}>
                        <CheckIcon width={16} height={16} />
                        {t(notice)}
                        {notice === 'editor.published' && job && (
                          <Link to={generatePath(paths.company.applicants, { jobId: String(job.id) })} className={ui.linkTone}>
                            {t('editor.toApplicants')}
                          </Link>
                        )}
                      </span>
                    ) : dirty ? (
                      t('editor.unsaved')
                    ) : published ? (
                      ''
                    ) : (
                      t('editor.publishHint')
                    )}
                  </span>
                  {job && status === 'draft' && (
                    <button ref={focus.triggerRef} type="button" className={cx(ui.btn, ui.quiet)} disabled={busy !== null} onClick={() => setConfirm('delete')}>
                      {t('editor.delete')}
                    </button>
                  )}
                  {published && (
                    <button ref={focus.triggerRef} type="button" className={cx(ui.btn, ui.quiet)} disabled={busy !== null} onClick={() => setConfirm('close')}>
                      {t('editor.close')}
                    </button>
                  )}
                  <button type="button" className={cx(ui.btn, published ? ui.primary : ui.secondary)} disabled={busy !== null || (!dirty && !!job)} onClick={onSave}>
                    {busy === 'save' ? t('editor.saving') : t('editor.save')}
                  </button>
                  {!published && (
                    <button type="button" className={cx(ui.btn, ui.primary)} disabled={busy !== null} onClick={onPublish}>
                      {busy === 'publish' ? t('editor.publishing') : t('editor.publish')}
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        <TwoWayPreview rows={rows} importance={(r) => importanceByName.get(`${r.name.trim()}|${Number(r.weight)}`)} />
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  error,
  className,
  hideLabel = false,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  hideLabel?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={cx(ui.field, className)}>
      <span className={hideLabel ? ui.visuallyHidden : ui.label}>{label}</span>
      {children}
      {error && (
        <span className={ui.error}>
          <AlertIcon width={14} height={14} />
          {error}
        </span>
      )}
      {hint && !error && <span className={ui.hint}>{hint}</span>}
    </label>
  );
}

function CriterionRow({
  index,
  row,
  locked,
  weightLocked,
  error,
  hits,
  onChange,
  onBlurCheck,
  onRemove,
}: {
  index: number;
  row: Row;
  /** Published: name, category and description are fixed; only the weight changes. */
  locked: boolean;
  weightLocked: boolean;
  error?: string;
  hits: GuardrailHit[];
  onChange: (patch: Partial<Row>) => void;
  onBlurCheck: () => void;
  onRemove: () => void;
}) {
  const invalid = Boolean(error) || hits.length > 0;
  return (
    <li className={s.crit}>
      <span className={s.critIndex}>{index + 1}</span>
      <label className={ui.field}>
        <span className={ui.visuallyHidden}>{t('editor.criterion.name')}</span>
        <input
          className={ui.input}
          value={row.name}
          maxLength={50}
          readOnly={locked}
          placeholder={t('editor.criterion.name')}
          aria-invalid={invalid || undefined}
          onChange={(e) => onChange({ name: e.target.value })}
          onBlur={onBlurCheck}
        />
      </label>
      <label className={ui.field}>
        <span className={ui.visuallyHidden}>{t('editor.criterion.category')}</span>
        <select className={ui.select} value={row.category} disabled={locked} onChange={(e) => onChange({ category: e.target.value as Category })}>
          {CATEGORIES.map((x) => (
            <option key={x} value={x}>
              {t(`category.${x}`)}
            </option>
          ))}
        </select>
      </label>
      <label className={cx(ui.field, s.weight)}>
        <span className={ui.visuallyHidden}>{t('editor.criterion.weight')}</span>
        <input
          className={ui.input}
          type="number"
          min={1}
          max={100}
          value={row.weight}
          readOnly={weightLocked}
          onChange={(e) => onChange({ weight: e.target.value })}
        />
        <span aria-hidden="true">%</span>
      </label>
      {locked ? (
        <span />
      ) : (
        <button
          type="button"
          className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)}
          aria-label={t('editor.criterion.remove', { name: row.name || String(index + 1) })}
          onClick={onRemove}
          style={{ marginTop: 4 }}
        >
          <TrashIcon width={16} height={16} />
        </button>
      )}
      <label className={cx(ui.field, s.critWide)}>
        <span className={ui.visuallyHidden}>{t('editor.criterion.description')}</span>
        <input
          className={ui.input}
          value={row.description}
          maxLength={500}
          readOnly={locked}
          placeholder={t('editor.criterion.descriptionPlaceholder')}
          onChange={(e) => onChange({ description: e.target.value })}
          onBlur={onBlurCheck}
        />
        {row.category === 'education' && !error && !locked && <span className={ui.hint}>{t('editor.criterion.educationHint')}</span>}
      </label>
      {hits.length > 0 && (
        <div className={cx(ui.blocked, s.critWide)} role="alert">
          <strong>
            <AlertIcon width={15} height={15} />
            {t('editor.blocked')}
          </strong>
          {hits.map((h, i) => (
            <span key={i}>
              {h.reason} {t('editor.blockedMatched', { text: h.matched })}
              {h.law_ref && <span className={ui.blockedLaw}> · {t('editor.blockedLaw', { law: h.law_ref })}</span>}
            </span>
          ))}
        </div>
      )}
      {!hits.length && error && (
        <span className={s.critWide}>
          <InlineError>{error}</InlineError>
        </span>
      )}
    </li>
  );
}

/**
 * One criteria set, two directions: what signed-in seekers read (name, category, importance; no weights, D1, D30)
 * and what the applicant ranking uses (weights). Importance comes from the last saved set.
 */
function TwoWayPreview({ rows, importance }: { rows: Row[]; importance: (r: Row) => Importance | undefined }) {
  return (
    <aside className={cx(ui.panel, s.preview)} aria-labelledby="preview-title">
      <h2 id="preview-title" className={ui.panelTitle} style={{ marginBottom: 14 }}>
        {t('editor.preview.title')}
      </h2>
      <section className={s.previewSide}>
        <h3 className={s.previewHead}>
          <span className={s.dot} />
          {t('editor.preview.seeker')}
        </h3>
        {rows.length === 0 ? (
          <p className={ui.caption}>{t('editor.preview.empty')}</p>
        ) : (
          <ul className={ui.list}>
            {rows.map((r) => {
              const level = importance(r);
              return (
                <li key={r.key} className={ui.listRow}>
                  <span className={ui.listName}>{r.name || '—'}</span>
                  <span className={ui.listEnd}>
                    <CategoryTag category={r.category} quiet />
                    {level ? <ImportanceTag level={level} /> : <span className={ui.categoryText}>—</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        <p className={ui.caption} style={{ marginTop: 8 }}>
          {t('editor.preview.seekerNote')}
        </p>
      </section>
      <section className={s.previewSide}>
        <h3 className={s.previewHead}>
          <span className={s.dot} data-side="company" />
          {t('editor.preview.company')}
        </h3>
        {rows.length === 0 ? (
          <p className={ui.caption}>{t('editor.preview.empty')}</p>
        ) : (
          <ul className={ui.list}>
            {rows.map((r) => (
              <li key={r.key} className={ui.listRow}>
                <span className={ui.listName}>{r.name || '—'}</span>
                <span className={s.weightText}>{Number(r.weight) || 0}%</span>
              </li>
            ))}
          </ul>
        )}
        <p className={ui.caption} style={{ marginTop: 8 }}>
          {t('editor.preview.companyNote')}
        </p>
      </section>
    </aside>
  );
}
