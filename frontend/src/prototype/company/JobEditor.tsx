import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { AlertIcon, CheckIcon } from '@/components/common/icons';
import {
  CATEGORIES,
  checkCriteria,
  EMPLOYMENT_TYPES,
  JD_DRAFT,
  jobById,
  MY_COMPANY,
  SUGGESTED_CRITERIA,
  type Category,
  type EmploymentType,
  type GuardrailHit,
  type Job,
} from '../data';
import { t, type ProtoKey } from '../i18n';
import { PlusIcon, TrashIcon, XIcon } from '../icons';
import { pp } from '../paths';
import { AiNotice, cx, Example, PageHead, ui } from '../ui';
import JobTabs from './JobTabs';
import s from './company.module.css';

interface EditCriterion {
  key: number;
  name: string;
  description: string;
  category: Category;
  weight: number;
}

const MAX_CRITERIA = 10;
// D13: an education criterion must name a major (or 이공계/STEM)
const MAJOR = /전공|학과|공학|컴퓨터|소프트웨어|통계|수학|물리|이공계|stem/i;
let nextKey = 1000;

export default function JobEditor() {
  const { jobId } = useParams();
  const source = jobId ? (jobById(Number(jobId)) ?? null) : null;
  // Remount on route change so /new and /:id/edit never share state
  return <Editor key={jobId ?? 'new'} source={source} />;
}

function Editor({ source }: { source: Job | null }) {
  const [form, setForm] = useState({
    title: source?.title ?? '',
    employment_type: (source?.employment_type ?? 'full_time') as EmploymentType,
    min_experience_years: source?.min_experience_years?.toString() ?? '',
    location: source?.location ?? '',
    salary_note: source?.salary_note ?? '',
    deadline: source?.deadline ?? '',
    description: source?.description ?? '',
  });
  const [criteria, setCriteria] = useState<EditCriterion[]>(
    source?.criteria.map((c) => ({ key: c.id, name: c.name, description: c.description, category: c.category, weight: c.weight })) ?? [],
  );
  const [status, setStatus] = useState(source?.status ?? 'draft');
  const [lit, setLit] = useState<number | null>(null);
  const [hits, setHits] = useState<GuardrailHit[]>([]);
  const [fieldErrors, setFieldErrors] = useState<(ProtoKey | null)[]>([]);
  const [totalError, setTotalError] = useState(false);
  const [saved, setSaved] = useState(false);

  const total = criteria.reduce((sum, c) => sum + (Number.isFinite(c.weight) ? c.weight : 0), 0);
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => (setForm((f) => ({ ...f, [k]: v })), setSaved(false));
  const updateCrit = (key: number, patch: Partial<EditCriterion>) => {
    setCriteria((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)));
    setSaved(false);
  };
  const addCrit = (c?: Partial<EditCriterion>) => {
    if (criteria.length >= MAX_CRITERIA) return;
    setCriteria((cs) => [...cs, { key: nextKey++, name: '', description: '', category: 'skill', weight: 0, ...c }]);
    setSaved(false);
  };

  // What PUT /api/jobs/{id}/criteria checks on save: names, D13 majors, the 100 total and the legal guardrail
  const save = () => {
    const errs = criteria.map((c): ProtoKey | null =>
      !c.name.trim() ? 'editor.nameRequired' : c.category === 'education' && !MAJOR.test(`${c.name} ${c.description}`) ? 'editor.majorRequired' : null,
    );
    const found = checkCriteria(criteria);
    setFieldErrors(errs);
    setHits(found);
    setTotalError(total !== 100);
    setSaved(found.length === 0 && errs.every((e) => !e) && total === 100);
  };

  const published = status === 'published';
  const canPublish = saved && form.description.trim() !== '' && form.title.trim() !== '' && status === 'draft';
  const job: Job | null = source && { ...source, status };

  return (
    <div className={ui.page} style={{ paddingBottom: 0 }}>
      {job ? <JobTabs job={job} /> : <PageHead title={t('editor.newTitle')} back={{ to: pp.company.jobs, label: t('jobTabs.back') }} />}

      <div className={s.editor}>
        <div className={ui.stack}>
          <section className={ui.panel}>
            <div className={ui.panelHead}>
              <h2 className={ui.panelTitle}>{t('editor.basics')}</h2>
              {source && <Example />}
            </div>
            <div className={s.grid3}>
              <label className={cx(ui.field, s.span2)}>
                <span className={ui.label}>{t('editor.titleLabel')}</span>
                <input className={ui.input} value={form.title} placeholder={t('editor.titlePlaceholder')} onChange={(e) => set('title', e.target.value)} />
              </label>
              <label className={ui.field}>
                <span className={ui.label}>{t('editor.employment')}</span>
                <select className={ui.select} value={form.employment_type} onChange={(e) => set('employment_type', e.target.value as EmploymentType)}>
                  {EMPLOYMENT_TYPES.map((x) => (
                    <option key={x} value={x}>
                      {t(`employment.${x}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className={ui.field}>
                <span className={ui.label}>{t('editor.minExperience')}</span>
                <input className={ui.input} type="number" min={0} max={30} value={form.min_experience_years} onChange={(e) => set('min_experience_years', e.target.value)} />
                <span className={ui.hint}>{t('editor.minExperienceHint')}</span>
              </label>
              <label className={ui.field}>
                <span className={ui.label}>{t('editor.location')}</span>
                <input className={ui.input} value={form.location} onChange={(e) => set('location', e.target.value)} />
              </label>
              <label className={ui.field}>
                <span className={ui.label}>{t('editor.deadline')}</span>
                <input className={ui.input} type="date" value={form.deadline} onChange={(e) => set('deadline', e.target.value)} />
                <span className={ui.hint}>{t('editor.deadlineHint')}</span>
              </label>
              <label className={cx(ui.field, s.span2)}>
                <span className={ui.label}>{t('editor.salary')}</span>
                <input className={ui.input} value={form.salary_note} onChange={(e) => set('salary_note', e.target.value)} />
                <span className={ui.hint}>{t('editor.salaryHint')}</span>
              </label>
            </div>
          </section>

          <JdSection value={form.description} onChange={(v) => set('description', v)} canDraft={status === 'draft'} />

          <section className={ui.panel}>
            <div className={ui.panelHead}>
              <div>
                <h2 className={ui.panelTitle}>
                  {t('editor.criteria')}
                  <span className={ui.count}>
                    {criteria.length}/{MAX_CRITERIA}
                  </span>
                </h2>
                <p className={ui.caption} style={{ marginTop: 4 }}>
                  {t('editor.criteriaLead')}
                </p>
              </div>
            </div>

            <Suggestions existing={criteria.map((c) => c.name)} onAdd={(c) => addCrit(c)} />

            {hits.length > 0 && (
              <p className={ui.error} role="alert" style={{ marginBottom: 12, fontSize: 13.5 }}>
                <AlertIcon width={16} height={16} />
                {t('editor.blockedAlert', { n: hits.length })}
              </p>
            )}

            <ul className={s.critList}>
              {criteria.map((c, i) => {
                const hit = hits.find((h) => h.index === i);
                const err = fieldErrors[i];
                return (
                  <li
                    key={c.key}
                    className={s.crit}
                    data-lit={lit === i || undefined}
                    data-blocked={hit || err ? true : undefined}
                    onMouseEnter={() => setLit(i)}
                    onMouseLeave={() => setLit(null)}
                    onFocus={() => setLit(i)}
                    onBlur={() => setLit(null)}
                  >
                    <span className={s.critIndex}>{i + 1}</span>
                    <label className={ui.field}>
                      <span className={ui.visuallyHidden}>{t('editor.criterion.name')}</span>
                      <input
                        className={ui.input}
                        value={c.name}
                        placeholder={t('editor.criterion.name')}
                        aria-invalid={hit || err ? true : undefined}
                        onChange={(e) => updateCrit(c.key, { name: e.target.value })}
                      />
                    </label>
                    <label className={ui.field}>
                      <span className={ui.visuallyHidden}>{t('editor.criterion.category')}</span>
                      <select className={ui.select} value={c.category} onChange={(e) => updateCrit(c.key, { category: e.target.value as Category })}>
                        {CATEGORIES.map((x) => (
                          <option key={x} value={x}>
                            {t(`category.${x}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className={cx(ui.field, s.weightInput)}>
                      <span className={ui.visuallyHidden}>{t('editor.criterion.weight')}</span>
                      <input
                        className={ui.input}
                        type="number"
                        min={1}
                        max={100}
                        value={c.weight}
                        onChange={(e) => updateCrit(c.key, { weight: Number(e.target.value) })}
                      />
                      <span aria-hidden="true">%</span>
                    </label>
                    <button
                      type="button"
                      className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)}
                      aria-label={t('editor.criterion.remove', { name: c.name || String(i + 1) })}
                      onClick={() => (setCriteria((cs) => cs.filter((x) => x.key !== c.key)), setHits([]), setFieldErrors([]), setSaved(false))}
                      style={{ marginTop: 4 }}
                    >
                      <TrashIcon width={16} height={16} />
                    </button>
                    <label className={cx(ui.field, s.critDesc)}>
                      <span className={ui.visuallyHidden}>{t('editor.criterion.description')}</span>
                      <input
                        className={ui.input}
                        value={c.description}
                        placeholder={t('editor.criterion.descriptionPlaceholder')}
                        onChange={(e) => updateCrit(c.key, { description: e.target.value })}
                      />
                      {c.category === 'education' && !err && <span className={ui.hint}>{t('editor.criterion.educationHint')}</span>}
                    </label>
                    {hit && (
                      <div className={cx(s.blockedBox, s.critError)} role="alert">
                        <strong>
                          <AlertIcon width={15} height={15} />
                          {t('editor.blocked')}
                        </strong>
                        <span>{hit.reason}</span>
                        <span>{t('editor.blockedMatched', { text: hit.matched })}</span>
                        <span className={s.law}>{t('editor.blockedLaw', { law: hit.law_ref })}</span>
                      </div>
                    )}
                    {!hit && err && (
                      <p className={cx(ui.error, s.critError)}>
                        <AlertIcon width={14} height={14} />
                        {t(err)}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>

            <div className={s.critFoot}>
              <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => addCrit()} disabled={criteria.length >= MAX_CRITERIA}>
                <PlusIcon width={15} height={15} />
                {t('editor.criterion.add')}
              </button>
              <span className={s.total}>
                {t('editor.total')}
                <span className={s.totalBar}>
                  <span className={s.totalFill} data-over={total > 100 || undefined} style={{ width: `${Math.min(total, 100)}%` }} />
                </span>
                <span className={s.totalValue}>{total} / 100</span>
              </span>
            </div>
            {totalError && total !== 100 && (
              <p className={ui.error} style={{ marginTop: 10 }}>
                <AlertIcon width={14} height={14} />
                {t('editor.totalError', { n: total })}
              </p>
            )}
          </section>

          <div className={s.footerBar}>
            <span className={s.footerNote} role="status">
              {published ? (
                <span className={ui.done}>
                  <CheckIcon width={16} height={16} />
                  {t('editor.published')}
                </span>
              ) : saved ? (
                <span className={ui.done}>
                  <CheckIcon width={16} height={16} />
                  {t('editor.saved')}
                </span>
              ) : (
                t('editor.publishHint')
              )}
            </span>
            {published && source ? (
              <Link to={pp.company.applicants(source.id)} className={cx(ui.btn, ui.primary)}>
                {t('editor.toApplicants')}
              </Link>
            ) : (
              <>
                <button type="button" className={cx(ui.btn, ui.secondary)} onClick={save}>
                  {t('editor.save')}
                </button>
                <button type="button" className={cx(ui.btn, ui.primary)} disabled={!canPublish} onClick={() => setStatus('published')}>
                  {t('editor.publish')}
                </button>
              </>
            )}
          </div>
        </div>

        <TwoWayPreview criteria={criteria} lit={lit} />
      </div>
    </div>
  );
}

function JdSection({ value, onChange, canDraft }: { value: string; onChange: (v: string) => void; canDraft: boolean }) {
  const [open, setOpen] = useState(false);
  const [keywords, setKeywords] = useState<string[]>(['Kubernetes', 'MLOps']);
  const [kw, setKw] = useState('');
  const [notes, setNotes] = useState('');
  const [projects, setProjects] = useState<number[]>([MY_COMPANY.projects[0].id]);
  const [phase, setPhase] = useState<'idle' | 'loading' | 'done'>('idle');
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    if (phase !== 'loading') return;
    const id = setTimeout(() => setPhase('done'), 1200);
    return () => clearTimeout(id);
  }, [phase]);

  const d = JD_DRAFT.sections;
  const draftText = [
    d.intro,
    '',
    t('editor.draft.responsibilities'),
    ...d.responsibilities.map((x) => `- ${x}`),
    '',
    t('editor.draft.requirements'),
    ...d.requirements.map((x) => `- ${x}`),
    '',
    t('editor.draft.preferred'),
    ...d.preferred.map((x) => `- ${x}`),
  ].join('\n');

  return (
    <section className={ui.panel}>
      <div className={ui.panelHead}>
        <h2 className={ui.panelTitle}>{t('editor.jd')}</h2>
        {canDraft && !open && (
          <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => setOpen(true)}>
            {t('editor.aiDraft')}
          </button>
        )}
      </div>
      <textarea className={ui.textarea} rows={11} value={value} placeholder={t('editor.jdPlaceholder')} aria-label={t('editor.jd')} onChange={(e) => onChange(e.target.value)} />
      {applied && (
        <p className={ui.done} style={{ marginTop: 10 }} role="status">
          <CheckIcon width={16} height={16} />
          {t('editor.draft.applied')}
        </p>
      )}

      {open && (
        <div className={s.draftBox}>
          <div className={s.draftHead}>
            <h3 className={s.draftTitle}>
              <span className={ui.aiBadge}>{t('common.ai')}</span>
              {t('editor.draft.title')}
            </h3>
            <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={t('common.close')} onClick={() => setOpen(false)}>
              <XIcon width={16} height={16} />
            </button>
          </div>
          <p className={ui.caption}>{t('editor.draft.lead')}</p>

          <div className={s.grid2}>
            <div className={ui.field}>
              <span className={ui.label}>{t('editor.draft.keywords')}</span>
              <div className={ui.chips}>
                {keywords.map((x) => (
                  <span key={x} className={ui.chip}>
                    {x}
                    <button type="button" aria-label={t('common.remove', { name: x })} onClick={() => setKeywords(keywords.filter((y) => y !== x))}>
                      <XIcon width={14} height={14} />
                    </button>
                  </span>
                ))}
              </div>
              <input
                className={ui.input}
                value={kw}
                placeholder={t('editor.draft.keywordsPlaceholder')}
                aria-label={t('editor.draft.keywords')}
                onChange={(e) => setKw(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== 'Enter') return;
                  e.preventDefault();
                  const v = kw.trim();
                  if (v && keywords.length < 10 && !keywords.includes(v)) setKeywords([...keywords, v]);
                  setKw('');
                }}
              />
            </div>
            <label className={ui.field}>
              <span className={ui.label}>{t('editor.draft.notes')}</span>
              <textarea className={ui.textarea} rows={3} value={notes} placeholder={t('editor.draft.notesPlaceholder')} onChange={(e) => setNotes(e.target.value)} />
            </label>
          </div>
          <fieldset className={ui.field} style={{ border: 0, margin: 0, padding: 0 }}>
            <legend className={ui.label} style={{ marginBottom: 8 }}>
              {t('editor.draft.projects')}
            </legend>
            <div className={s.checkGroup}>
              {MY_COMPANY.projects.map((p) => (
                <label key={p.id} className={ui.checkLine}>
                  <input
                    type="checkbox"
                    checked={projects.includes(p.id)}
                    onChange={(e) => setProjects(e.target.checked ? [...projects, p.id] : projects.filter((x) => x !== p.id))}
                  />
                  {p.name}
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <button type="button" className={cx(ui.btn, ui.primary)} disabled={phase === 'loading'} onClick={() => (setPhase('loading'), setApplied(false))}>
              {phase === 'loading' ? t('editor.draft.generating') : t('editor.draft.generate')}
            </button>
          </div>

          {phase === 'loading' && (
            <div className={s.draftOut} aria-busy="true">
              {[90, 70, 80, 55].map((w) => (
                <div key={w} className={ui.skeleton} style={{ width: `${w}%` }} />
              ))}
            </div>
          )}

          {phase === 'done' && (
            <>
              <AiNotice method="rules" />
              <div className={s.draftOut}>
                <div>
                  <h4>{t('editor.draft.intro')}</h4>
                  <p className={ui.body}>{d.intro}</p>
                </div>
                {(['responsibilities', 'requirements', 'preferred'] as const).map((k) => (
                  <div key={k}>
                    <h4>{t(`editor.draft.${k}`)}</h4>
                    <ul>
                      {d[k].map((x) => (
                        <li key={x}>{x}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
              <div>
                <h4 className={ui.sectionTitle}>{t('editor.draft.dropped', { n: JD_DRAFT.dropped.length })}</h4>
                <p className={ui.caption} style={{ marginBottom: 8 }}>
                  {t('editor.draft.droppedLead')}
                </p>
                <ul className={s.dropped}>
                  {JD_DRAFT.dropped.map((x) => (
                    <li key={x.text} className={s.droppedItem}>
                      <span className={s.droppedText}>{x.text}</span>
                      <span className={ui.muted}>{x.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
                <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => (onChange(draftText), setApplied(true), setOpen(false))}>
                  {t('editor.draft.apply')}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function Suggestions({ existing, onAdd }: { existing: string[]; onAdd: (c: Partial<EditCriterion>) => void }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <div style={{ marginBottom: 16 }}>
        <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => setOpen(true)}>
          {t('editor.suggest')}
        </button>
      </div>
    );
  }
  return (
    <div className={s.suggest}>
      <div className={s.draftHead}>
        <h3 className={s.draftTitle}>
          <span className={ui.aiBadge}>{t('common.ai')}</span>
          {t('editor.suggest.title')}
        </h3>
        <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={t('common.close')} onClick={() => setOpen(false)}>
          <XIcon width={16} height={16} />
        </button>
      </div>
      <AiNotice method="rules" />
      {SUGGESTED_CRITERIA.items.map((c) => {
        const added = existing.includes(c.name);
        return (
          <div key={c.name} className={s.suggestRow}>
            <span>{c.name}</span>
            <span className={ui.tag}>{t(`category.${c.category}`)}</span>
            <span className={s.weightPill}>{c.weight}%</span>
            <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} disabled={added} onClick={() => onAdd({ name: c.name, category: c.category, weight: c.weight, description: '' })}>
              {added ? t('editor.suggest.added') : t('editor.suggest.add')}
            </button>
          </div>
        );
      })}
      <div>
        <h4 className={ui.sectionTitle}>{t('editor.suggest.blocked')}</h4>
        {SUGGESTED_CRITERIA.blocked.map((b) => (
          <p key={b.name} className={ui.caption}>
            <strong>{b.name}</strong> · {b.reason}
          </p>
        ))}
      </div>
    </div>
  );
}

/** The signature: one criterion lights its row in what seekers see and in the applicant ranking at once. */
function TwoWayPreview({ criteria, lit }: { criteria: EditCriterion[]; lit: number | null }) {
  const total = criteria.reduce((sum, c) => sum + (c.weight || 0), 0) || 1;
  return (
    <aside className={s.aside} aria-label={t('editor.preview.title')}>
      <div>
        <h2 className={ui.panelTitle}>{t('editor.preview.title')}</h2>
        <p className={ui.caption} style={{ marginTop: 2 }}>
          {t('editor.preview.lead')}
        </p>
      </div>
      <section className={s.preview}>
        <div className={s.previewHead}>
          <span className={s.previewTitle}>
            <span className={s.previewDot} />
            {t('editor.preview.seeker')}
          </span>
        </div>
        {criteria.length === 0 ? (
          <p className={ui.caption}>{t('editor.preview.empty')}</p>
        ) : (
          <ul className={s.previewRows} data-active={lit !== null || undefined}>
            {criteria.map((c, i) => (
              <li key={c.key} className={s.previewRow} data-side="seeker" data-lit={lit === i || undefined}>
                <span className={ui.truncate}>{c.name || '—'}</span>
                <span className={ui.tag}>{t(`category.${c.category}`)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className={s.previewNote}>{t('editor.preview.seekerNote')}</p>
      </section>
      <section className={s.preview}>
        <div className={s.previewHead}>
          <span className={s.previewTitle}>
            <span className={s.previewDot} data-side="company" />
            {t('editor.preview.company')}
          </span>
        </div>
        {criteria.length === 0 ? (
          <p className={ui.caption}>{t('editor.preview.empty')}</p>
        ) : (
          <ul className={s.previewRows} data-active={lit !== null || undefined}>
            {criteria.map((c, i) => (
              <li key={c.key} className={s.previewRow} data-side="company" data-lit={lit === i || undefined}>
                <span className={ui.truncate}>{c.name || '—'}</span>
                <span className={s.weightPill}>{Math.round(((c.weight || 0) / total) * 100)}%</span>
              </li>
            ))}
          </ul>
        )}
        <p className={s.previewNote}>{t('editor.preview.companyNote')}</p>
      </section>
    </aside>
  );
}
