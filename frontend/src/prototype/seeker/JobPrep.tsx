import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { AlertIcon, CheckIcon } from '@/components/common/icons';
import { jobById, PREP, type CvReviewItem } from '../data';
import { t } from '../i18n';
import { BookIcon, ClipboardCheckIcon, ExternalIcon, MessageIcon } from '../icons';
import { pp } from '../paths';
import { AiNotice, cx, Example, JobMeta, PageHead, ui, useProtoState } from '../ui';
import s from './seeker.module.css';

type Tab = 'gaps' | 'interview' | 'review';
const TABS: { id: Tab; icon: typeof BookIcon }[] = [
  { id: 'gaps', icon: BookIcon },
  { id: 'interview', icon: MessageIcon },
  { id: 'review', icon: ClipboardCheckIcon },
];

/** Job prep (D21, D25): gaps are skills the job names that the CV text lacks; nothing comes from company scores. */
export default function JobPrep() {
  const { jobId } = useParams();
  const job = jobById(Number(jobId)) ?? jobById(101)!;
  const [params] = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get('tab') as Tab) || 'gaps');
  const [state, stateBar] = useProtoState([
    { id: 'ok', label: 'prep.state.ok' },
    { id: 'none', label: 'prep.state.none' },
  ]);

  return (
    <div className={ui.page}>
      {stateBar}
      <PageHead
        title={`${t('prep.title')} · ${job.title}`}
        lead={t('prep.lead')}
        back={{ to: pp.seeker.job(job.id), label: job.title }}
        extra={
          <div className={s.jobHeadTop} style={{ marginTop: 10 }}>
            <JobMeta job={job} />
            <Example />
          </div>
        }
      />

      <div className={ui.tabs} role="tablist">
        {TABS.map(({ id, icon: Icon }) => (
          <button key={id} type="button" role="tab" className={ui.tab} aria-selected={tab === id} onClick={() => setTab(id)}>
            <Icon width={16} height={16} />
            {t(`prep.tab.${id}`)}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'gaps' && (state === 'none' ? <NoGaps /> : <Gaps />)}
        {tab === 'interview' && <Interview />}
        {tab === 'review' && <Review />}
      </div>
    </div>
  );
}

function NoGaps() {
  return (
    <div className={ui.stack}>
      <AiNotice method="rules" />
      <section className={ui.panel}>
        <div className={ui.empty}>
          <span className={ui.done}>
            <CheckIcon width={18} height={18} />
          </span>
          <p className={ui.emptyTitle}>{t('prep.none.title')}</p>
          <p className={ui.emptyBody}>{t('prep.none.body')}</p>
        </div>
      </section>
    </div>
  );
}

function Gaps() {
  return (
    <div className={ui.stack}>
      <AiNotice method="rules" />
      <div className={s.prepGrid}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>
              {t('prep.gaps.title')}
              <span className={ui.count}>{PREP.gaps.length}</span>
            </h2>
            <Example />
          </div>
          <ul className={ui.rows}>
            {PREP.gaps.map((g) => (
              <li key={g.name} className={ui.gapRow}>
                <span className={ui.gapName}>
                  <AlertIcon width={15} height={15} />
                  {g.name}
                  <span className={ui.tag}>{t(`prep.kind.${g.kind}`)}</span>
                </span>
                <span className={ui.gapBadge}>{t('prep.gaps.missing')}</span>
              </li>
            ))}
          </ul>
          <p className={ui.caption} style={{ marginTop: 14 }}>
            {t('prep.gaps.lead')}
          </p>
        </section>

        <section aria-labelledby="roadmap-title">
          <h2 id="roadmap-title" className={ui.panelTitle}>
            {t('prep.roadmap.title')}
          </h2>
          <p className={ui.caption} style={{ margin: '4px 0 14px' }}>
            {t('prep.roadmap.lead')}
          </p>
          <ol className={s.steps}>
            {PREP.steps.map((step) => (
              <li key={step.order} className={s.step}>
                <span className={s.stepIndex}>{step.order}</span>
                <div className={s.stepBody}>
                  <span className={s.stepHead}>
                    {step.skill}
                    <span className={ui.tag}>{t(`prep.kind.${step.kind}`)}</span>
                  </span>
                  <p className={ui.body}>
                    <strong>{t('prep.roadmap.goal')}</strong> · {step.goal}
                  </p>
                  <div className={s.stepCols}>
                    <div>
                      <h3 className={ui.sectionTitle}>{t('prep.roadmap.activities')}</h3>
                      <ul className={s.plainList}>
                        {step.activities.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h3 className={ui.sectionTitle}>{t('prep.roadmap.resources')}</h3>
                      {step.resources.map((r) => (
                        <a key={r.url} className={s.resource} href={r.url} target="_blank" rel="noreferrer">
                          {r.title}
                          <ExternalIcon width={14} height={14} />
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}

function Interview() {
  return (
    <div className={ui.stack}>
      <AiNotice method="rules" />
      <div>
        <h2 className={ui.panelTitle}>
          {t('prep.q.title', { n: PREP.questions.length })}
          <Example />
        </h2>
        <p className={ui.caption} style={{ margin: '4px 0 14px' }}>
          {t('prep.q.lead')}
        </p>
        {PREP.questions.map((q, i) => (
          <article key={q.question} className={s.question}>
            <p className={s.questionText}>
              <span className={s.questionIndex}>{String(i + 1).padStart(2, '0')}</span>
              <span>{q.question}</span>
            </p>
            <div className={s.questionMeta}>
              <div className={ui.stack} style={{ gap: 10 }}>
                <span className={s.tagRow}>
                  <span className={cx(ui.tag, ui.tagTone)}>{t(`prep.q.kind.${q.kind}`)}</span>
                  <span className={ui.tag}>{q.criterion_name ?? t('prep.q.general')}</span>
                </span>
                <div>
                  <h3 className={ui.sectionTitle}>{t('prep.q.intent')}</h3>
                  <p className={ui.body}>{q.intent}</p>
                </div>
                {q.cv_quote && (
                  <div>
                    <h3 className={ui.sectionTitle}>{t('prep.q.quote')}</h3>
                    <p className={ui.quote}>{q.cv_quote}</p>
                  </div>
                )}
              </div>
              <div>
                <h3 className={ui.sectionTitle}>{t('prep.q.tips')}</h3>
                <ul className={s.plainList}>
                  {q.answer_tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function ReviewList({ items }: { items: CvReviewItem[] }) {
  const sorted = [...items].sort((a, b) => Number(b.affects_scoring) - Number(a.affects_scoring));
  return (
    <div>
      {sorted.map((x) => (
        <div key={x.title} className={s.reviewItem}>
          <h3 className={s.reviewTitle}>
            {x.title}
            {x.affects_scoring && <span className={cx(ui.tag, ui.tagTone)}>{t('prep.review.affects')}</span>}
          </h3>
          <p className={ui.body}>{x.detail}</p>
          {x.cv_quote && <p className={ui.quote}>{x.cv_quote}</p>}
        </div>
      ))}
    </div>
  );
}

function Review() {
  return (
    <div className={ui.stack}>
      <AiNotice method="rules" />
      <div>
        <h2 className={ui.panelTitle}>{t('prep.review.title')}</h2>
        <p className={ui.caption} style={{ margin: '4px 0 0' }}>
          {t('prep.review.lead')}
        </p>
      </div>
      <div className={s.reviewCols}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h3 className={ui.panelTitle}>
              {t('prep.review.strengths')}
              <span className={ui.count}>{PREP.review.strengths.length}</span>
            </h3>
            <Example />
          </div>
          <ReviewList items={PREP.review.strengths} />
        </section>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h3 className={ui.panelTitle}>
              {t('prep.review.improvements')}
              <span className={ui.count}>{PREP.review.improvements.length}</span>
            </h3>
            <Example />
          </div>
          <ReviewList items={PREP.review.improvements} />
          <p className={ui.caption} style={{ marginTop: 16 }}>
            {t('prep.review.affectsNote')}
          </p>
        </section>
      </div>
    </div>
  );
}
