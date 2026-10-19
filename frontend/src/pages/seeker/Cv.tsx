import { useEffect, useRef, useState, type ChangeEvent, type ReactNode, type Ref } from 'react';
import { Link, useLocation } from 'react-router';
import { ApiError, api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { consentPath } from '@/auth/AuthContext';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate, monthsLabel } from '@/components/common/format';
import { CheckIcon, ClipboardCheckIcon, DocumentIcon, InfoIcon, PlusIcon, UploadIcon, XIcon } from '@/components/common/icons';
import { cx, PageHead } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading, Notice } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import ReviewResult from '@/components/seeker/ReviewResult';
import s from '@/components/seeker/seeker.module.css';
import { t, type MessageKey } from '@/i18n';
import type { CvOut, CvProfile, CvReviewOut } from '@/types/cv';

// Same limit as the backend (ai.parsing.pdf MAX_BYTES); checked here only to answer before the upload
const MAX_BYTES = 5 * 1024 * 1024;

const MASKED: Record<string, MessageKey> = {
  name: 'masked.name',
  email: 'masked.email',
  phone: 'masked.phone',
  url: 'masked.url',
  rrn: 'masked.rrn',
  birth: 'masked.birth',
  address: 'masked.address',
};

async function loadCv(): Promise<CvOut | null> {
  try {
    return await api.myCv();
  } catch (e) {
    if (errorCode(e) === 'CV_NOT_FOUND') return null;
    throw e;
  }
}

/** Upload a text PDF, check what the AI read, edit and confirm it. Every save is a new version (cv_service.update). */
export default function Cv() {
  const { state, setData, reload } = useApi(loadCv, []);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<unknown>(null);
  // The version a save just produced; CvView remounts for it (key = profile id) and says "saved"
  const [savedId, setSavedId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const pick = () => fileRef.current?.click();
  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploadError(null);
    if (file.size > MAX_BYTES) {
      setUploadError(new ApiError(422, 'CV_TOO_LARGE', ''));
      return;
    }
    setUploading(true);
    try {
      setData(await api.uploadCv(file));
    } catch (err) {
      setUploadError(err);
    } finally {
      setUploading(false);
    }
  };

  let content;
  if (state.status === 'loading') content = <Loading rows={6} />;
  else if (state.status === 'error') content = <ErrorPanel error={state.error} onRetry={reload} />;
  else if (uploading) content = <Processing />;
  else if (!state.data) content = <Upload onPick={pick} error={uploadError} />;
  else {
    content = (
      <CvView
        key={state.data.id}
        cv={state.data}
        justSaved={savedId === state.data.id}
        onSaved={(next) => (setData(next), setSavedId(next.id))}
        onEdit={() => setSavedId(null)}
        onReupload={pick}
        uploadError={uploadError}
      />
    );
  }

  return (
    <div className={ui.page}>
      <PageHead title={t('cv.title')} lead={t('cv.lead')} />
      <input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={onFile} />
      {content}
    </div>
  );
}

function UploadError({ error }: { error: unknown }) {
  const location = useLocation();
  return (
    <InlineError>
      {errorText(error)}{' '}
      {errorCode(error) === 'AI_CONSENT_REQUIRED' && <Link to={consentPath(location.pathname)}>{t('shell.withdrawnAction')}</Link>}
    </InlineError>
  );
}

/** No CV yet: one column, the upload is the only thing on the page. */
function Upload({ onPick, error }: { onPick: () => void; error: unknown }) {
  return (
    <section className={cx(s.dropzone, s.cvColumn)}>
      <span className={s.dropIcon}>
        <UploadIcon width={22} height={22} />
      </span>
      <p className={ui.emptyTitle}>{t('cv.upload.title')}</p>
      <p className={ui.emptyBody}>{t('cv.upload.body')}</p>
      <button type="button" className={cx(ui.btn, ui.primary)} onClick={onPick}>
        {t('cv.upload.pick')}
      </button>
      {error != null && <UploadError error={error} />}
      <p className={ui.caption}>
        {t('cv.upload.limits')}
        <br />
        {t('cv.upload.mask')} {t('cv.upload.consent')}
      </p>
    </section>
  );
}

function Processing() {
  return (
    <section className={cx(ui.panel, s.cvColumn)} aria-busy="true">
      <p className={ui.caption}>{t('cv.processing')}</p>
      <div style={{ marginTop: 16 }}>
        <Loading rows={5} panel={false} />
      </div>
    </section>
  );
}

/** Only while editing: edits tell scoring what to look for, they never add to what the PDF text proves (AI rule 14). */
function RuleCard() {
  return (
    <section className={s.ruleCard}>
      <h2>
        <InfoIcon width={16} height={16} />
        {t('cv.rule.title')}
      </h2>
      <p>{t('cv.rule.body')}</p>
    </section>
  );
}

function CvView({
  cv,
  justSaved,
  onSaved,
  onEdit,
  onReupload,
  uploadError,
}: {
  cv: CvOut;
  justSaved: boolean;
  onSaved: (cv: CvOut) => void;
  onEdit: () => void;
  onReupload: () => void;
  uploadError: unknown;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CvProfile>(cv.profile);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const focus = useConfirmFocus<HTMLButtonElement, HTMLTextAreaElement>(editing);
  const savedRef = useRef<HTMLParagraphElement>(null);

  // This version was just saved (CvView remounted for it): say so where focus is
  useEffect(() => {
    if (justSaved) savedRef.current?.focus();
  }, [justSaved]);

  // Confirming as it is and saving edits both create the next version (method "seeker")
  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const next = await api.updateCv(cv.id, { profile: editing ? draft : cv.profile, confirm: true });
      onSaved(next);
    } catch (e) {
      setSaveError(e);
      setSaving(false);
    }
  };
  const cancel = () => (setEditing(false), setDraft(cv.profile), setSaveError(null));

  const masked = cv.masked_kinds.map((k) => (MASKED[k] ? t(MASKED[k]) : k)).join(', ');
  const meta = [
    t('cv.version', { v: cv.version }),
    formatDate(cv.created_at),
    cv.method === 'seeker' ? t('cv.versionSeeker') : t('cv.versionAi'),
    masked && t('cv.masked', { kinds: masked }),
    t('cv.totalExperience', { value: monthsLabel(cv.total_experience_months) }),
  ].filter(Boolean);

  return (
    <div className={s.cvColumn}>
      {/* One header for the file and its version; the page's actions sit on its right */}
      <header className={s.cvHead}>
        <span className={s.fileIcon}>
          <DocumentIcon width={20} height={20} />
        </span>
        <div className={s.cvHeadText}>
          <span className={s.fileName}>
            {t('cv.file', { name: cv.file_name, pages: cv.pages })}
            <span className={cx(ui.tag, cv.confirmed && ui.tagTone)}>{cv.confirmed ? t('cv.confirmed') : t('cv.unconfirmed')}</span>
          </span>
          <span className={ui.meta}>
            {meta.map((m, i) => (
              <span key={i} className={ui.withIcon}>
                {i > 0 && <span className={ui.sep}>·</span>}
                {m}
              </span>
            ))}
          </span>
        </div>
        {!editing && (
          <div className={ui.actions}>
            <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={onReupload}>
              <UploadIcon width={15} height={15} />
              {t('cv.reupload')}
            </button>
            <button
              ref={focus.triggerRef}
              type="button"
              className={cx(ui.btn, ui.secondary)}
              onClick={() => (setEditing(true), onEdit())}
            >
              {t('cv.edit')}
            </button>
            {!cv.confirmed && (
              <button type="button" className={cx(ui.btn, ui.primary)} disabled={saving} onClick={save}>
                {saving ? t('cv.saving') : t('cv.confirm')}
              </button>
            )}
          </div>
        )}
      </header>

      {uploadError != null && <UploadError error={uploadError} />}
      {!editing && saveError != null && <InlineError>{errorText(saveError)}</InlineError>}
      {justSaved && !editing ? (
        <p ref={savedRef} tabIndex={-1} className={ui.done} role="status">
          <CheckIcon width={16} height={16} />
          {t('cv.confirmedDone', { v: cv.version })}
        </p>
      ) : (
        !cv.confirmed &&
        !editing && (
          <Notice>
            {t('cv.reviewBanner')} {t('cv.newVersionHint', { v: cv.version + 1 })}
          </Notice>
        )
      )}
      {editing && <RuleCard />}

      <section className={ui.panel} aria-label={t('cv.title')}>
        <AiNotice notice={cv.notice} method={cv.method} />
        <div style={{ marginTop: 20 }}>
          <ProfileView
            profile={editing ? draft : cv.profile}
            editing={editing}
            update={(patch) => setDraft((p) => ({ ...p, ...patch }))}
            firstFieldRef={focus.regionRef}
          />
        </div>
      </section>

      {editing ? (
        // Stays in view at the bottom while scrolling through a long form
        <div className={s.saveBar}>
          <span className={s.saveBarText}>
            {saveError != null ? <InlineError>{errorText(saveError)}</InlineError> : t('cv.newVersionHint', { v: cv.version + 1 })}
          </span>
          <button type="button" className={cx(ui.btn, ui.quiet)} disabled={saving} onClick={cancel}>
            {t('cv.cancelEdit')}
          </button>
          <button type="button" className={cx(ui.btn, ui.primary)} disabled={saving} onClick={save}>
            {saving ? t('cv.saving') : t('cv.saveEdit')}
          </button>
        </div>
      ) : (
        <CheckPanel cv={cv} />
      )}
    </div>
  );
}

/** 이력서 점검 (D25) of the version on screen, confirmed or not. Runs only when asked. */
function CheckPanel({ cv }: { cv: CvOut }) {
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState<CvReviewOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setReview(await api.reviewCv(cv.id));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={ui.panel} aria-labelledby="cv-check">
      <div className={ui.panelHead}>
        <div>
          <h2 id="cv-check" className={ui.panelTitle}>
            <ClipboardCheckIcon width={18} height={18} />
            {t('cv.check.title')}
          </h2>
          <p className={ui.caption} style={{ marginTop: 4 }}>
            {t('cv.check.lead')}
          </p>
        </div>
        {!review && (
          <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} disabled={busy} onClick={run}>
            {busy ? t('cv.check.running') : t('cv.check.run')}
          </button>
        )}
      </div>
      {busy && <Loading rows={4} panel={false} />}
      {error != null && (
        <InlineError>
          {errorText(error)}{' '}
          {errorCode(error) === 'AI_CONSENT_REQUIRED' && <Link to={consentPath(location.pathname)}>{t('shell.withdrawnAction')}</Link>}
        </InlineError>
      )}
      {review && <ReviewResult review={review} />}
    </section>
  );
}

function period(start: string | null, end: string | null) {
  const f = (d: string) => d.replace('-', '.');
  if (!start && !end) return '';
  return `${start ? f(start) : ''} – ${end ? f(end) : t('cv.present')}`;
}

/** The CV line an item was read from: the evidence, kept as a quiet caption. */
function Source({ text }: { text: string }) {
  if (!text) return null;
  return (
    <span className={s.sourceLine}>
      <span className={s.sourceLabel}>{t('cv.source')}</span>
      <span>{text}</span>
    </span>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className={s.section}>
      <h3 className={s.sectionHead}>
        {title}
        {count !== undefined && <span className={ui.count}>{count}</span>}
      </h3>
      {children}
    </section>
  );
}

/**
 * The structured CV; in edit mode the fields a seeker may correct (scores still read only the PDF text, AI rule 14).
 * Sections the AI found nothing for are left out in view mode; summary and skills stay editable.
 */
function ProfileView({
  profile,
  editing,
  update,
  firstFieldRef,
}: {
  profile: CvProfile;
  editing: boolean;
  update: (p: Partial<CvProfile>) => void;
  /** The first editable field; it takes focus when editing starts. */
  firstFieldRef?: Ref<HTMLTextAreaElement>;
}) {
  const [newSkill, setNewSkill] = useState('');
  const addSkill = () => {
    const v = newSkill.trim().replace(/\s+/g, ' ');
    if (v && !profile.skills.some((x) => x.toLowerCase() === v.toLowerCase())) update({ skills: [...profile.skills, v] });
    setNewSkill('');
  };

  const nothing =
    !profile.summary &&
    !profile.skills.length &&
    !profile.experiences.length &&
    !profile.projects.length &&
    !profile.education.length &&
    !profile.certificates.length;
  if (nothing && !editing) return <p className={ui.caption}>{t('cv.emptySection')}</p>;

  return (
    <>
      {(editing || profile.summary) && (
        <Section title={t('cv.summary')}>
          {editing ? (
            <textarea
              ref={firstFieldRef}
              className={ui.textarea}
              rows={2}
              maxLength={500}
              value={profile.summary}
              aria-label={t('cv.summary')}
              onChange={(e) => update({ summary: e.target.value })}
            />
          ) : (
            <p className={ui.body}>{profile.summary}</p>
          )}
        </Section>
      )}

      {(editing || profile.skills.length > 0) && (
        <Section title={t('cv.skills')} count={profile.skills.length}>
          {profile.skills.length > 0 && (
            <div className={ui.chips}>
              {profile.skills.map((x) => (
                <span key={x} className={editing ? s.skillChip : ui.tag}>
                  {x}
                  {editing && (
                    <button type="button" aria-label={t('common.remove', { name: x })} onClick={() => update({ skills: profile.skills.filter((y) => y !== x) })}>
                      <XIcon width={14} height={14} />
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
          {editing && (
            <div className={ui.chipInput} style={{ marginTop: 10, maxWidth: 360 }}>
              <input
                className={ui.input}
                value={newSkill}
                maxLength={100}
                placeholder={t('cv.skillAddPlaceholder')}
                aria-label={t('cv.skillAdd')}
                onChange={(e) => setNewSkill(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
              />
              <button type="button" className={cx(ui.btn, ui.secondary)} onClick={addSkill}>
                <PlusIcon width={15} height={15} />
                {t('common.add')}
              </button>
            </div>
          )}
        </Section>
      )}

      {profile.experiences.length > 0 && (
        <Section title={t('cv.experiences')}>
          {profile.experiences.map((x, i) => (
            <div key={i} className={s.entry}>
              <span className={s.entryPeriod}>{period(x.start, x.end)}</span>
              <div className={s.entryBody}>
                {editing ? (
                  <div className={s.editGrid}>
                    <label className={ui.field}>
                      <span className={ui.label}>{t('cv.org')}</span>
                      <input className={ui.input} value={x.org} readOnly />
                    </label>
                    <label className={ui.field}>
                      <span className={ui.label}>{t('cv.role')}</span>
                      <input
                        className={ui.input}
                        value={x.role}
                        maxLength={100}
                        onChange={(e) => update({ experiences: profile.experiences.map((y, j) => (j === i ? { ...y, role: e.target.value } : y)) })}
                      />
                    </label>
                    <label className={ui.field} style={{ gridColumn: '1 / -1' }}>
                      <span className={ui.label}>{t('cv.descriptionLabel')}</span>
                      <textarea
                        className={ui.textarea}
                        rows={2}
                        maxLength={2000}
                        value={x.description}
                        onChange={(e) => update({ experiences: profile.experiences.map((y, j) => (j === i ? { ...y, description: e.target.value } : y)) })}
                      />
                    </label>
                  </div>
                ) : (
                  <>
                    <span className={s.entryTitle}>{[x.org, x.role].filter(Boolean).join(' · ')}</span>
                    {x.description && <p className={ui.body}>{x.description}</p>}
                  </>
                )}
                <Source text={x.source} />
              </div>
            </div>
          ))}
        </Section>
      )}

      {profile.projects.length > 0 && (
        <Section title={t('cv.projects')}>
          {profile.projects.map((x, i) => (
            <div key={i} className={s.entry}>
              <span className={s.entryPeriod}>{x.role}</span>
              <div className={s.entryBody}>
                <span className={s.entryTitle}>{x.name}</span>
                {editing ? (
                  <textarea
                    className={ui.textarea}
                    rows={2}
                    maxLength={2000}
                    value={x.description}
                    aria-label={t('cv.descriptionLabel')}
                    onChange={(e) => update({ projects: profile.projects.map((y, j) => (j === i ? { ...y, description: e.target.value } : y)) })}
                  />
                ) : (
                  x.description && <p className={ui.body}>{x.description}</p>
                )}
                {x.tech.length > 0 && (
                  <span className={s.tagRow}>
                    {x.tech.map((tech) => (
                      <span key={tech} className={ui.tag}>
                        {tech}
                      </span>
                    ))}
                  </span>
                )}
                <Source text={x.source} />
              </div>
            </div>
          ))}
        </Section>
      )}

      {profile.education.length > 0 && (
        <Section title={t('cv.education')}>
          {profile.education.map((x, i) => (
            <div key={i} className={s.entry}>
              <span className={s.entryPeriod}>{x.degree}</span>
              <div className={s.entryBody}>
                {editing ? (
                  <div className={s.editGrid}>
                    <label className={ui.field}>
                      <span className={ui.label}>{t('cv.major')}</span>
                      <input
                        className={ui.input}
                        value={x.major}
                        maxLength={100}
                        onChange={(e) => update({ education: profile.education.map((y, j) => (j === i ? { ...y, major: e.target.value } : y)) })}
                      />
                    </label>
                  </div>
                ) : (
                  <span className={s.entryTitle}>{[x.school, x.major].filter(Boolean).join(' · ')}</span>
                )}
                <Source text={x.source} />
              </div>
            </div>
          ))}
        </Section>
      )}

      {profile.certificates.length > 0 && (
        <Section title={t('cv.certificates')}>
          {profile.certificates.map((x, i) => (
            <div key={i} className={s.entry}>
              <span className={s.entryPeriod}>{x.date?.replace('-', '.')}</span>
              <div className={s.entryBody}>
                <span className={s.entryTitle}>{x.name}</span>
                <Source text={x.source} />
              </div>
            </div>
          ))}
        </Section>
      )}
    </>
  );
}
