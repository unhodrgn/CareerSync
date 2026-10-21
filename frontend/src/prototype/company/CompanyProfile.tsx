import { useState } from 'react';
import { Link } from 'react-router';
import { AlertIcon, CheckIcon } from '@/components/common/icons';
import { MY_COMPANY, type CompanyProject } from '../data';
import { t } from '../i18n';
import { PencilIcon, PlusIcon, TrashIcon, XIcon } from '../icons';
import { pp } from '../paths';
import { cx, Example, PageHead, ui } from '../ui';
import s from './company.module.css';

const MAX_PROJECTS = 20;
let nextId = 100;

/** Company profile (intro, 인재상) and running projects CRUD (D23). */
export default function CompanyProfile() {
  const [name, setName] = useState(MY_COMPANY.name);
  const [intro, setIntro] = useState(MY_COMPANY.intro);
  const [talent, setTalent] = useState(MY_COMPANY.talent_profile);
  const [saved, setSaved] = useState(false);
  const [projects, setProjects] = useState(MY_COMPANY.projects);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const saveProject = (p: CompanyProject) => {
    setProjects((ps) => (ps.some((x) => x.id === p.id) ? ps.map((x) => (x.id === p.id ? p : x)) : [...ps, p]));
    setEditing(null);
  };

  return (
    <div className={ui.page}>
      <PageHead
        title={t('cprof.title')}
        lead={t('cprof.lead')}
        actions={
          <Link to={pp.seeker.job(101)} className={cx(ui.btn, ui.secondary)}>
            {t('cprof.preview')}
          </Link>
        }
      />
      <div className={s.editor}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>
              {t('cprof.info')}
              <Example />
            </h2>
          </div>
          <div className={ui.stack} style={{ gap: 16 }}>
            <label className={ui.field}>
              <span className={ui.label}>{t('cprof.name')}</span>
              <input className={ui.input} value={name} maxLength={100} onChange={(e) => (setName(e.target.value), setSaved(false))} />
            </label>
            <label className={ui.field}>
              <span className={ui.label}>{t('cprof.intro')}</span>
              <textarea className={ui.textarea} rows={4} maxLength={1000} value={intro} onChange={(e) => (setIntro(e.target.value), setSaved(false))} />
              <span className={s.counter}>{t('cprof.count', { n: intro.length })}</span>
            </label>
            <label className={ui.field}>
              <span className={ui.label}>{t('cprof.talentProfile')}</span>
              <textarea className={ui.textarea} rows={4} maxLength={1000} value={talent} onChange={(e) => (setTalent(e.target.value), setSaved(false))} />
              <span className={s.counter}>{t('cprof.count', { n: talent.length })}</span>
            </label>
          </div>
          <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
            <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => setSaved(true)}>
              {t('cprof.save')}
            </button>
            {saved && (
              <span className={ui.done} role="status">
                <CheckIcon width={16} height={16} />
                {t('common.saved')}
              </span>
            )}
          </div>
        </section>

        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>
              {t('cprof.projects')}
              <span className={ui.count}>
                {projects.length}/{MAX_PROJECTS}
              </span>
            </h2>
          </div>
          <p className={ui.caption} style={{ marginBottom: 14 }}>
            {t('cprof.projectsLead')}
          </p>
          <ul className={s.projects}>
            {projects.map((p) =>
              editing === p.id ? (
                <li key={p.id}>
                  <ProjectForm project={p} onSave={saveProject} onCancel={() => setEditing(null)} />
                </li>
              ) : (
                <li key={p.id} className={s.projectItem}>
                  <span className={s.projectName}>{p.name}</span>
                  <span className={s.rowActions}>
                    {deleting === p.id ? (
                      <>
                        <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => (setProjects((ps) => ps.filter((x) => x.id !== p.id)), setDeleting(null))}>
                          {t('common.delete')}
                        </button>
                        <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={() => setDeleting(null)}>
                          {t('common.cancel')}
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={`${t('common.edit')} ${p.name}`} onClick={() => setEditing(p.id)}>
                          <PencilIcon width={15} height={15} />
                        </button>
                        <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={`${t('common.delete')} ${p.name}`} onClick={() => setDeleting(p.id)}>
                          <TrashIcon width={15} height={15} />
                        </button>
                      </>
                    )}
                  </span>
                  {deleting === p.id ? (
                    <p className={ui.caption} style={{ gridColumn: '1 / -1' }}>
                      {t('cprof.deleteConfirm')}
                    </p>
                  ) : (
                    <>
                      <p className={ui.caption} style={{ gridColumn: '1 / -1' }}>
                        {p.description}
                      </p>
                      <span className={ui.chips} style={{ gridColumn: '1 / -1', gap: 4 }}>
                        {p.techs.map((x) => (
                          <span key={x} className={ui.tag}>
                            {x}
                          </span>
                        ))}
                      </span>
                    </>
                  )}
                </li>
              ),
            )}
            {editing === 'new' && (
              <li>
                <ProjectForm project={{ id: nextId++, name: '', description: '', techs: [] }} onSave={saveProject} onCancel={() => setEditing(null)} />
              </li>
            )}
          </ul>
          {editing !== 'new' && (
            <button
              type="button"
              className={cx(ui.btn, ui.secondary, ui.small)}
              style={{ marginTop: 12 }}
              disabled={projects.length >= MAX_PROJECTS}
              onClick={() => setEditing('new')}
            >
              <PlusIcon width={15} height={15} />
              {t('cprof.addProject')}
            </button>
          )}
        </section>
      </div>
    </div>
  );
}

function ProjectForm({ project, onSave, onCancel }: { project: CompanyProject; onSave: (p: CompanyProject) => void; onCancel: () => void }) {
  const [p, setP] = useState(project);
  const [tech, setTech] = useState('');
  const [error, setError] = useState(false);
  const addTech = () => {
    const v = tech.trim();
    if (v && p.techs.length < 20 && !p.techs.some((x) => x.toLowerCase() === v.toLowerCase())) setP({ ...p, techs: [...p.techs, v] });
    setTech('');
  };
  return (
    <div className={s.projectForm}>
      <label className={ui.field}>
        <span className={ui.label}>{t('cprof.projectName')}</span>
        <input className={ui.input} value={p.name} maxLength={200} aria-invalid={error || undefined} onChange={(e) => (setP({ ...p, name: e.target.value }), setError(false))} />
        {error && (
          <p className={ui.error}>
            <AlertIcon width={14} height={14} />
            {t('cprof.projectNameRequired')}
          </p>
        )}
      </label>
      <label className={ui.field}>
        <span className={ui.label}>{t('cprof.projectDescription')}</span>
        <textarea className={ui.textarea} rows={2} maxLength={2000} value={p.description} onChange={(e) => setP({ ...p, description: e.target.value })} />
      </label>
      <div className={ui.field}>
        <span className={ui.label}>{t('cprof.projectTechs')}</span>
        {p.techs.length > 0 && (
          <div className={ui.chips}>
            {p.techs.map((x) => (
              <span key={x} className={ui.chip}>
                {x}
                <button type="button" aria-label={t('common.remove', { name: x })} onClick={() => setP({ ...p, techs: p.techs.filter((y) => y !== x) })}>
                  <XIcon width={14} height={14} />
                </button>
              </span>
            ))}
          </div>
        )}
        <input
          className={ui.input}
          value={tech}
          placeholder={t('cprof.projectTechsPlaceholder')}
          aria-label={t('cprof.projectTechs')}
          onChange={(e) => setTech(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTech())}
        />
      </div>
      <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
        <button type="button" className={cx(ui.btn, ui.primary, ui.small)} onClick={() => (p.name.trim() ? onSave({ ...p, name: p.name.trim() }) : setError(true))}>
          {t('cprof.projectSave')}
        </button>
        <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>
    </div>
  );
}
