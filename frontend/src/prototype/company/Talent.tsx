import { useState } from 'react';
import { useParams } from 'react-router';
import { CheckIcon } from '@/components/common/icons';
import { jobById, TALENT, type Job, type TalentCandidate } from '../data';
import { t } from '../i18n';
import { ClockIcon, LockIcon, UserIcon } from '../icons';
import { AiNotice, cx, Example, ui } from '../ui';
import { scoreLevel } from './Applicants';
import JobTabs from './JobTabs';
import s from './company.module.css';

/** GET /api/jobs/{id}/talent: anonymous opt-in seekers with verified facts only (D3, D19); offers (D20). */
export default function Talent() {
  const { jobId } = useParams();
  const job = jobById(Number(jobId)) ?? jobById(101)!;
  const items = job.id === 101 ? TALENT.items : [];
  return (
    <div className={ui.page}>
      <JobTabs job={job} />
      <p className={ui.lead} style={{ margin: '0 0 16px' }}>
        {t('talent.lead')}
      </p>
      <div className={ui.stack} style={{ gap: 12, marginBottom: 20 }}>
        <AiNotice method="rules" />
        <p className={s.hidden}>
          <LockIcon width={15} height={15} />
          {t('talent.anonNote')}
        </p>
        <p className={s.hidden}>
          <ClockIcon width={15} height={15} />
          {t('talent.pending', { n: TALENT.pending_count })} {t('talent.limit')}
        </p>
      </div>
      <div className={s.talentList}>
        {items.map((c) => (
          <TalentCard key={c.anonymous_id} candidate={c} job={job} />
        ))}
      </div>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  if (!items.length) return <span className={ui.muted}>{t('talent.none')}</span>;
  return (
    <>
      {items.map((x) => (
        <span key={x} className={ui.tag}>
          {x}
        </span>
      ))}
    </>
  );
}

function TalentCard({ candidate: c, job }: { candidate: TalentCandidate; job: Job }) {
  const [composing, setComposing] = useState(false);
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(c.offer_status === 'pending');
  const [justSent, setJustSent] = useState(false);

  return (
    <article className={s.talent}>
      <div>
        <span className={s.anonId}>
          <span className={s.anonAvatar} aria-hidden="true">
            <UserIcon width={16} height={16} />
          </span>
          {c.anonymous_id}
        </span>
        <div className={s.critSquares}>
          {job.criteria.map((cr) => {
            const score = c.criteria.find((x) => x.criterion_id === cr.id)?.score ?? 0;
            return (
              <span key={cr.id} className={s.critSquare}>
                <span className={s.square} data-level={scoreLevel(score)} />
                <span className={ui.truncate}>{cr.name}</span>
                <span>{score}</span>
              </span>
            );
          })}
        </div>
      </div>

      <dl className={s.facts}>
        <dt>{t('talent.skills')}</dt>
        <dd>
          <List items={c.skills} />
        </dd>
        <dt>{t('talent.experience')}</dt>
        <dd>{t('talent.experienceValue', { n: c.experience_years })}</dd>
        <dt>{t('talent.roles')}</dt>
        <dd>{c.roles.join(', ')}</dd>
        <dt>{t('talent.projectTechs')}</dt>
        <dd>
          <List items={c.project_techs} />
        </dd>
        <dt>{t('talent.education')}</dt>
        <dd>{c.education.map((e) => `${e.degree} · ${e.major}`).join(', ')}</dd>
        <dt>{t('talent.certificates')}</dt>
        <dd>
          <List items={c.certificates} />
        </dd>
        <dt>{t('talent.desired')}</dt>
        <dd>
          {[...c.desired.locations, ...c.desired.employment_types.map((x) => t(`employment.${x}`)), ...c.desired.job_keywords].join(' · ')}
        </dd>
      </dl>

      <div className={s.talentSide}>
        <span className={ui.caption}>{t('talent.fit')}</span>
        <span className={s.fitBig}>{c.fit}</span>
        <Example />
        {sent ? (
          <span className={ui.status} data-status="pending">
            {t('talent.offerSent')}
          </span>
        ) : (
          !composing && (
            <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => setComposing(true)}>
              {t('talent.offer')}
            </button>
          )
        )}
      </div>

      {composing && !sent && (
        <div className={cx(ui.inlineConfirm, s.composer)}>
          <label className={ui.field}>
            <span className={ui.label}>{t('talent.composer.label')}</span>
            <textarea
              className={ui.textarea}
              rows={3}
              maxLength={1000}
              value={message}
              placeholder={t('talent.composer.placeholder')}
              onChange={(e) => setMessage(e.target.value)}
            />
            <span className={s.counter}>{t('talent.composer.count', { n: message.length })}</span>
          </label>
          <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
            <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => (setSent(true), setJustSent(true), setComposing(false))}>
              {t('talent.composer.send')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} onClick={() => setComposing(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
      {justSent && (
        <p className={cx(ui.done, s.composer)} role="status">
          <CheckIcon width={16} height={16} />
          {t('talent.composer.sent')}
        </p>
      )}
    </article>
  );
}
