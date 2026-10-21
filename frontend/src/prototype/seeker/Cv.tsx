import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { CheckIcon, DocumentIcon, InfoIcon } from '@/components/common/icons';
import { CV, formatDate, type CvProfile } from '../data';
import { t } from '../i18n';
import { PlusIcon, UploadIcon, XIcon } from '../icons';
import { pp } from '../paths';
import { AiNotice, cx, Example, monthsLabel, PageHead, ui, Undecided, useProtoState } from '../ui';
import s from './seeker.module.css';

// Skills the AI read from the PDF; anything the seeker adds on top is not in the CV text (AI rule 14)
const PDF_SKILLS = CV.profile.skills.filter((x) => x !== 'Docker');
const EXTRACTED: CvProfile = { ...CV.profile, skills: PDF_SKILLS };

interface Version {
  v: number;
  method: 'rules' | 'seeker';
  date: string;
}

export default function Cv() {
  const [state, stateBar] = useProtoState([
    { id: 'extracted', label: 'cv.state.extracted' },
    { id: 'empty', label: 'cv.state.empty' },
    { id: 'confirmed', label: 'cv.state.confirmed' },
  ]);
  return (
    <div className={ui.page}>
      {stateBar}
      <PageHead title={t('cv.title')} lead={t('cv.lead')} />
      <CvFlow key={state} start={state} />
    </div>
  );
}

function CvFlow({ start }: { start: string }) {
  const [phase, setPhase] = useState<'empty' | 'processing' | 'review'>(start === 'empty' ? 'empty' : 'review');
  const [profile, setProfile] = useState<CvProfile>(start === 'confirmed' ? CV.profile : EXTRACTED);
  const [versions, setVersions] = useState<Version[]>(
    start === 'confirmed'
      ? [
          { v: 1, method: 'rules', date: '2026-10-15' },
          { v: 2, method: 'seeker', date: '2026-10-15' },
        ]
      : [{ v: 1, method: 'rules', date: '2026-10-15' }],
  );
  const [confirmed, setConfirmed] = useState(start === 'confirmed');
  const [editing, setEditing] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const current = versions[versions.length - 1];

  useEffect(() => {
    if (phase !== 'processing') return;
    const id = setTimeout(() => setPhase('review'), 1400);
    return () => clearTimeout(id);
  }, [phase]);

  if (phase === 'empty') {
    return (
      <div className={s.cvLayout}>
        <section className={s.dropzone}>
          <span className={s.dropIcon}>
            <UploadIcon width={22} height={22} />
          </span>
          <p className={ui.emptyTitle}>{t('cv.upload.title')}</p>
          <p className={ui.emptyBody}>{t('cv.upload.body')}</p>
          <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => setPhase('processing')}>
            {t('cv.upload.pick')}
          </button>
          <p className={ui.caption}>
            {t('cv.upload.mask')} {t('cv.upload.consent')}
          </p>
        </section>
        <RuleCard />
      </div>
    );
  }

  if (phase === 'processing') {
    return (
      <div className={s.cvLayout}>
        <section className={ui.panel} aria-busy="true">
          <p className={ui.caption}>{t('cv.processing')}</p>
          <div className={ui.stack} style={{ marginTop: 16 }}>
            {[70, 92, 55, 84, 40].map((w) => (
              <div key={w} className={ui.skeleton} style={{ width: `${w}%` }} />
            ))}
          </div>
        </section>
        <RuleCard />
      </div>
    );
  }

  // Saving edits makes a new version; confirming the AI's reading as it is keeps the version
  const save = () => {
    if (editing) setVersions((vs) => [...vs, { v: vs.length + 1, method: 'seeker', date: '2026-10-17' }]);
    setEditing(false);
    setConfirmed(true);
    setJustSaved(true);
  };

  const update = (patch: Partial<CvProfile>) => setProfile((p) => ({ ...p, ...patch }));

  return (
    <div className={s.cvLayout}>
      <div className={ui.stack}>
        <div className={s.fileBar}>
          <span className={s.fileIcon}>
            <DocumentIcon width={20} height={20} />
          </span>
          <span className={s.fileText}>
            <span className={s.fileName}>
              {t('cv.file', { name: CV.file_name, pages: CV.pages })}
              <Example />
            </span>
            <span className={ui.meta}>
              <span>{t('cv.version', { v: current.v })}</span>
              <span className={ui.sep}>·</span>
              <span>{t('cv.masked', { kinds: CV.masked_kinds.map((k) => t(`masked.${k as 'name' | 'email' | 'phone'}`)).join(', ') })}</span>
              <span className={ui.sep}>·</span>
              <span>{t('cv.totalExperience', { value: monthsLabel(CV.total_experience_months) })}</span>
            </span>
          </span>
          <span className={cx(ui.tag, confirmed && ui.tagTone)}>{confirmed ? t('cv.confirmed') : t('cv.unconfirmed')}</span>
        </div>

        {justSaved && !editing ? (
          <p className={ui.done} role="status">
            <CheckIcon width={16} height={16} />
            {t('cv.confirmedDone', { v: current.v })}
          </p>
        ) : (
          !confirmed && (
            <p className={ui.aiNotice}>
              <InfoIcon width={16} height={16} />
              {t('cv.reviewBanner')}
            </p>
          )
        )}

        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>
              {t('cv.title')}
              <Example />
            </h2>
            <div className={ui.actions}>
              {!editing && (
                <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => { setEditing(true); setJustSaved(false); }}>
                  {t('cv.edit')}
                </button>
              )}
              {(editing || !confirmed) && (
                <button type="button" className={cx(ui.btn, ui.primary, ui.small)} onClick={save}>
                  {editing && confirmed ? t('cv.saveEdit') : t('cv.confirm')}
                </button>
              )}
            </div>
          </div>
          <AiNotice method={current.method} />
          <div style={{ marginTop: 20 }}>
            <ProfileView profile={profile} editing={editing} update={update} />
          </div>
        </section>
      </div>

      <aside className={ui.stack}>
        <RuleCard />
        <section className={ui.panel}>
          <h2 className={ui.sectionTitle}>{t('cv.history')}</h2>
          <ul className={s.history}>
            {[...versions].reverse().map((x) => (
              <li key={x.v} className={s.historyItem} data-current={x.v === current.v || undefined}>
                <span className={s.historyVersion}>{t('cv.version', { v: x.v })}</span>
                <span>{x.method === 'rules' ? t('cv.historyAi') : t('cv.historySeeker')}</span>
                <span className={cx(ui.caption, ui.num)}>{formatDate(x.date)}</span>
              </li>
            ))}
          </ul>
          <p className={ui.caption} style={{ marginTop: 12 }}>
            {t('cv.historyNote')}
          </p>
        </section>
        <section className={ui.panel}>
          <p className={ui.caption}>{t('cv.selfCheck')}</p>
          <Link to={`${pp.seeker.prep(101)}?tab=review`} className={ui.linkTone}>
            {t('cv.selfCheckLink')}
          </Link>
        </section>
        <section className={ui.panel}>
          <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => setPhase('processing')}>
            <UploadIcon width={15} height={15} />
            {t('cv.reupload')}
          </button>
          <div style={{ marginTop: 12 }}>
            <Undecided q="Q13" later>
              {t('cv.deleteLater')}
            </Undecided>
          </div>
        </section>
      </aside>
    </div>
  );
}

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

function period(start: string | null, end: string | null) {
  const f = (d: string) => d.replace('-', '.');
  return `${start ? f(start) : ''} – ${end ? f(end) : t('cv.present')}`;
}

function ProfileView({ profile, editing, update }: { profile: CvProfile; editing: boolean; update: (p: Partial<CvProfile>) => void }) {
  const [newSkill, setNewSkill] = useState('');
  const addSkill = () => {
    const v = newSkill.trim();
    if (v && !profile.skills.some((x) => x.toLowerCase() === v.toLowerCase())) update({ skills: [...profile.skills, v] });
    setNewSkill('');
  };

  return (
    <>
      <section className={s.section}>
        <h3 className={s.sectionHead}>{t('cv.summary')}</h3>
        {editing ? (
          <textarea className={ui.textarea} rows={2} value={profile.summary} aria-label={t('cv.summary')} onChange={(e) => update({ summary: e.target.value })} />
        ) : (
          <p className={ui.body}>{profile.summary}</p>
        )}
      </section>

      <section className={s.section}>
        <h3 className={s.sectionHead}>
          {t('cv.skills')} <span className={ui.count}>{profile.skills.length}</span>
        </h3>
        <div className={ui.chips}>
          {profile.skills.map((x) => {
            const added = !PDF_SKILLS.includes(x);
            return (
              <span key={x} className={s.skillChip} data-added={added || undefined}>
                {x}
                {added && <span className={s.skillNote}>{t('cv.skillNotInPdf')}</span>}
                {editing && (
                  <button type="button" aria-label={t('common.remove', { name: x })} onClick={() => update({ skills: profile.skills.filter((y) => y !== x) })}>
                    <XIcon width={14} height={14} />
                  </button>
                )}
              </span>
            );
          })}
        </div>
        {editing && (
          <div className={ui.chipInput} style={{ marginTop: 10, maxWidth: 360 }}>
            <input
              className={ui.input}
              value={newSkill}
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
      </section>

      <section className={s.section}>
        <h3 className={s.sectionHead}>{t('cv.experiences')}</h3>
        {profile.experiences.map((x, i) => (
          <div key={x.org} className={s.entry}>
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
                      onChange={(e) => update({ experiences: profile.experiences.map((y, j) => (j === i ? { ...y, role: e.target.value } : y)) })}
                    />
                  </label>
                  <label className={ui.field} style={{ gridColumn: '1 / -1' }}>
                    <span className={ui.label}>{t('cv.descriptionLabel')}</span>
                    <textarea
                      className={ui.textarea}
                      rows={2}
                      value={x.description}
                      onChange={(e) => update({ experiences: profile.experiences.map((y, j) => (j === i ? { ...y, description: e.target.value } : y)) })}
                    />
                  </label>
                </div>
              ) : (
                <>
                  <span className={s.entryTitle}>
                    {x.org} · {x.role}
                  </span>
                  <p className={ui.body}>{x.description}</p>
                </>
              )}
              <Source text={x.source} />
            </div>
          </div>
        ))}
      </section>

      <section className={s.section}>
        <h3 className={s.sectionHead}>{t('cv.projects')}</h3>
        {profile.projects.map((x, i) => (
          <div key={x.name} className={s.entry}>
            <span className={s.entryPeriod}>{x.role}</span>
            <div className={s.entryBody}>
              <span className={s.entryTitle}>{x.name}</span>
              {editing ? (
                <textarea
                  className={ui.textarea}
                  rows={2}
                  value={x.description}
                  aria-label={t('cv.descriptionLabel')}
                  onChange={(e) => update({ projects: profile.projects.map((y, j) => (j === i ? { ...y, description: e.target.value } : y)) })}
                />
              ) : (
                <p className={ui.body}>{x.description}</p>
              )}
              <span className={s.tagRow}>
                {x.tech.map((tech) => (
                  <span key={tech} className={ui.tag}>
                    {tech}
                  </span>
                ))}
              </span>
              <Source text={x.source} />
            </div>
          </div>
        ))}
      </section>

      <section className={s.section}>
        <h3 className={s.sectionHead}>{t('cv.education')}</h3>
        {profile.education.map((x, i) => (
          <div key={x.school} className={s.entry}>
            <span className={s.entryPeriod}>{x.degree}</span>
            <div className={s.entryBody}>
              {editing ? (
                <div className={s.editGrid}>
                  <label className={ui.field}>
                    <span className={ui.label}>{t('cv.major')}</span>
                    <input
                      className={ui.input}
                      value={x.major}
                      onChange={(e) => update({ education: profile.education.map((y, j) => (j === i ? { ...y, major: e.target.value } : y)) })}
                    />
                  </label>
                </div>
              ) : (
                <span className={s.entryTitle}>
                  {x.school} · {x.major}
                </span>
              )}
              <Source text={x.source} />
            </div>
          </div>
        ))}
      </section>

      <section className={s.section}>
        <h3 className={s.sectionHead}>{t('cv.certificates')}</h3>
        {profile.certificates.map((x) => (
          <div key={x.name} className={s.entry}>
            <span className={s.entryPeriod}>{x.date?.replace('-', '.')}</span>
            <div className={s.entryBody}>
              <span className={s.entryTitle}>{x.name}</span>
              <Source text={x.source} />
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

function Source({ text }: { text: string }) {
  return (
    <span className={s.sourceLine}>
      <span className={s.sourceLabel}>{t('cv.source')}</span>
      <span>{text}</span>
    </span>
  );
}
