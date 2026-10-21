import { useState, type Ref } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { CheckIcon, PencilIcon, PlusIcon, TrashIcon, XIcon } from '@/components/common/icons';
import { cx, PageHead } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import s from '@/components/company/company.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { MAX_PROJECTS, PROJECT_MAX_TECHS, type CompanyOut, type CompanyProjectIn, type CompanyProjectOut } from '@/types/company';

/** Company profile (name, intro, 인재상) and running projects (D23): shown to signed-in users, never used in scoring. */
export default function CompanyProfile() {
  const company = useApi(() => api.myCompany(), []);
  const projects = useApi(() => api.myProjects(), []);

  return (
    <div className={ui.page}>
      <PageHead
        title={t('page.company.companyProfile.title')}
        lead={t('cprof.lead')}
        actions={
          company.state.status === 'ok' && (
            <Link to={generatePath(paths.companyPublic, { companyId: String(company.state.data.id) })} className={cx(ui.btn, ui.secondary)}>
              {t('cprof.preview')}
            </Link>
          )
        }
      />
      <div className={s.profileGrid}>
        {company.state.status === 'loading' && <Loading rows={6} />}
        {company.state.status === 'error' && <ErrorPanel error={company.state.error} onRetry={company.reload} />}
        {company.state.status === 'ok' && <InfoForm initial={company.state.data} onSaved={company.setData} />}

        {projects.state.status === 'loading' && <Loading rows={4} />}
        {projects.state.status === 'error' && <ErrorPanel error={projects.state.error} onRetry={projects.reload} />}
        {projects.state.status === 'ok' && <Projects items={projects.state.data} onChange={projects.setData} />}
      </div>
    </div>
  );
}

function InfoForm({ initial, onSaved }: { initial: CompanyOut; onSaved: (c: CompanyOut) => void }) {
  const [name, setName] = useState(initial.name);
  const [intro, setIntro] = useState(initial.intro);
  const [talent, setTalent] = useState(initial.talent_profile);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [nameError, setNameError] = useState(false);

  const save = async () => {
    if (!name.trim()) return setNameError(true);
    setBusy(true);
    setError(null);
    try {
      const saved = await api.updateMyCompany({ name: name.trim(), intro, talent_profile: talent });
      onSaved(saved);
      setDone(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const dirty = () => setDone(false);

  return (
    <section className={ui.panel} aria-labelledby="company-info">
      <h2 id="company-info" className={ui.panelTitle} style={{ marginBottom: 16 }}>
        {t('cprof.info')}
      </h2>
      <div className={ui.stack} style={{ gap: 16 }}>
        <label className={ui.field}>
          <span className={ui.label}>{t('cprof.name')}</span>
          <input
            className={ui.input}
            value={name}
            maxLength={100}
            aria-invalid={nameError || undefined}
            onChange={(e) => (setName(e.target.value), setNameError(false), dirty())}
          />
          {nameError && <InlineError>{t('cprof.nameRequired')}</InlineError>}
        </label>
        <label className={ui.field}>
          <span className={ui.label}>{t('cprof.intro')}</span>
          <textarea className={ui.textarea} rows={4} maxLength={1000} value={intro} onChange={(e) => (setIntro(e.target.value), dirty())} />
          <span className={s.counter}>{t('cprof.count', { n: intro.length })}</span>
        </label>
        <label className={ui.field}>
          <span className={ui.label}>{t('cprof.talentProfile')}</span>
          <textarea className={ui.textarea} rows={4} maxLength={1000} value={talent} onChange={(e) => (setTalent(e.target.value), dirty())} />
          <span className={s.counter}>{t('cprof.count', { n: talent.length })}</span>
        </label>
      </div>
      <div className={ui.actions} style={{ marginTop: 16, justifyContent: 'flex-start' }}>
        <button type="button" className={cx(ui.btn, ui.primary)} disabled={busy} onClick={save}>
          {busy ? t('editor.saving') : t('cprof.save')}
        </button>
        {done && (
          <span className={ui.done} role="status">
            <CheckIcon width={16} height={16} />
            {t('common.saved')}
          </span>
        )}
        {error != null && <InlineError>{errorText(error)}</InlineError>}
      </div>
    </section>
  );
}

function Projects({ items, onChange }: { items: CompanyProjectOut[]; onChange: (p: CompanyProjectOut[]) => void }) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const addFocus = useConfirmFocus<HTMLButtonElement, HTMLDivElement>(editing === 'new');

  return (
    <section className={ui.panel} aria-labelledby="projects-title">
      <h2 id="projects-title" className={ui.panelTitle}>
        {t('cprof.projects')}
        <span className={ui.count}>
          {items.length}/{MAX_PROJECTS}
        </span>
      </h2>
      <p className={ui.caption} style={{ margin: '4px 0 8px' }}>
        {t('cprof.projectsLead')}
      </p>
      {items.length === 0 && editing !== 'new' && <p className={ui.caption}>{t('cprof.projectsEmpty')}</p>}
      <ul className={cx(s.critList, ui.stagger)}>
        {items.map((p) =>
          editing === p.id ? (
            <li key={p.id} className={s.projectRow}>
              <ProjectForm
                project={p}
                onCancel={() => setEditing(null)}
                onSaved={(saved) => (onChange(items.map((x) => (x.id === saved.id ? saved : x))), setEditing(null))}
              />
            </li>
          ) : (
            <ProjectRow key={p.id} project={p} onEdit={() => setEditing(p.id)} onDeleted={() => onChange(items.filter((x) => x.id !== p.id))} />
          ),
        )}
        {editing === 'new' && (
          <li className={s.projectRow}>
            <ProjectForm
              regionRef={addFocus.regionRef}
              onCancel={() => setEditing(null)}
              onSaved={(saved) => (onChange([...items, saved]), setEditing(null))}
            />
          </li>
        )}
      </ul>
      {editing !== 'new' && (
        <button
          ref={addFocus.triggerRef}
          type="button"
          className={cx(ui.btn, ui.secondary, ui.small)}
          style={{ marginTop: 12 }}
          disabled={items.length >= MAX_PROJECTS}
          onClick={() => setEditing('new')}
        >
          <PlusIcon width={15} height={15} />
          {t('cprof.addProject')}
        </button>
      )}
    </section>
  );
}

function ProjectRow({ project: p, onEdit, onDeleted }: { project: CompanyProjectOut; onEdit: () => void; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement>(confirm);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deleteProject(p.id);
      onDeleted();
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <li className={s.projectRow}>
      <span className={s.projectName}>{p.name}</span>
      <span className={ui.actions}>
        {!confirm && (
          <>
            <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={t('cprof.editProject', { name: p.name })} onClick={onEdit}>
              <PencilIcon width={15} height={15} />
            </button>
            <button
              ref={focus.triggerRef}
              type="button"
              className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)}
              aria-label={t('cprof.deleteProject', { name: p.name })}
              onClick={() => setConfirm(true)}
            >
              <TrashIcon width={15} height={15} />
            </button>
          </>
        )}
      </span>
      {p.description && <p className={cx(ui.caption, s.projectWide)}>{p.description}</p>}
      {p.techs.length > 0 && (
        <span className={cx(ui.chips, s.projectWide)} style={{ gap: 4 }}>
          {p.techs.map((x) => (
            <span key={x} className={ui.tag}>
              {x}
            </span>
          ))}
        </span>
      )}
      {confirm && (
        <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t('cprof.deleteConfirm')} className={cx(ui.inlineConfirm, s.projectWide)}>
          <strong>{t('cprof.deleteConfirm')}</strong>
          {error != null && <InlineError>{errorText(error)}</InlineError>}
          <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
            <button type="button" className={cx(ui.btn, ui.secondary)} disabled={busy} onClick={remove}>
              {t('common.delete')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={() => setConfirm(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

function ProjectForm({
  project,
  regionRef,
  onSaved,
  onCancel,
}: {
  project?: CompanyProjectOut;
  regionRef?: Ref<HTMLDivElement>;
  onSaved: (p: CompanyProjectOut) => void;
  onCancel: () => void;
}) {
  const [p, setP] = useState<CompanyProjectIn>({ name: project?.name ?? '', description: project?.description ?? '', techs: project?.techs ?? [] });
  const [tech, setTech] = useState('');
  const [nameError, setNameError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const addTech = () => {
    const v = tech.trim().replace(/\s+/g, ' ');
    if (v && v.length <= 100 && p.techs.length < PROJECT_MAX_TECHS && !p.techs.some((x) => x.toLowerCase() === v.toLowerCase())) setP({ ...p, techs: [...p.techs, v] });
    setTech('');
  };

  const save = async () => {
    if (!p.name.trim()) return setNameError(true);
    setBusy(true);
    setError(null);
    try {
      const body = { ...p, name: p.name.trim() };
      onSaved(project ? await api.updateProject(project.id, body) : await api.createProject(body));
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <div ref={regionRef} tabIndex={-1} className={cx(ui.inlineConfirm, s.projectWide)} role="group" aria-label={project ? t('cprof.editProject', { name: project.name }) : t('cprof.addProject')}>
      <label className={ui.field}>
        <span className={ui.label}>{t('cprof.projectName')}</span>
        <input
          className={ui.input}
          value={p.name}
          maxLength={200}
          aria-invalid={nameError || undefined}
          // Editing an existing project: the form opens in its place, focus goes to the name
          autoFocus={!regionRef}
          onChange={(e) => (setP({ ...p, name: e.target.value }), setNameError(false))}
        />
        {nameError && <InlineError>{t('cprof.projectNameRequired')}</InlineError>}
      </label>
      <label className={ui.field}>
        <span className={ui.label}>{t('cprof.projectDescription')}</span>
        <textarea className={ui.textarea} rows={2} maxLength={2000} value={p.description} onChange={(e) => setP({ ...p, description: e.target.value })} />
      </label>
      <div className={ui.field}>
        <span className={ui.label}>
          {t('cprof.projectTechs')}{' '}
          <span className={ui.muted}>
            {p.techs.length}/{PROJECT_MAX_TECHS}
          </span>
        </span>
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
        <div className={ui.chipInput}>
          <input
            className={ui.input}
            value={tech}
            maxLength={100}
            placeholder={t('cprof.projectTechsPlaceholder')}
            aria-label={t('cprof.projectTechs')}
            onChange={(e) => setTech(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTech())}
          />
          <button type="button" className={cx(ui.btn, ui.secondary)} onClick={addTech}>
            <PlusIcon width={15} height={15} />
            {t('common.add')}
          </button>
        </div>
      </div>
      {error != null && <InlineError>{errorText(error)}</InlineError>}
      <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
        <button type="button" className={cx(ui.btn, ui.secondary)} disabled={busy} onClick={save}>
          {t('cprof.projectSave')}
        </button>
        <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>
    </div>
  );
}
