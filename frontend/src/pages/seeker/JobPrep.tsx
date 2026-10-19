import { useState } from 'react';
import { generatePath, useParams, useSearchParams } from 'react-router';
import { api } from '@/api/client';
import { errorCode } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { AlertIcon, BookIcon, CheckIcon, ClipboardCheckIcon, ExternalIcon, MessageIcon } from '@/components/common/icons';
import { JobMeta } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import ReviewResult from '@/components/seeker/ReviewResult';
import SeekerGate from '@/components/seeker/SeekerGate';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { InterviewOut, RoadmapOut } from '@/types/career';

type Tab = 'gaps' | 'interview' | 'review';
const TABS: { id: Tab; icon: typeof BookIcon }[] = [
  { id: 'gaps', icon: BookIcon },
  { id: 'interview', icon: MessageIcon },
  { id: 'review', icon: ClipboardCheckIcon },
];
const isTab = (v: string | null): v is Tab => v === 'gaps' || v === 'interview' || v === 'review';

/**
 * Job prep (D21, D25): gaps are skills and certificates the job names that the CV text lacks, computed by code;
 * nothing here comes from company scores. Each tab asks the server only when first opened, then stays loaded.
 */
export default function JobPrep() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const job = useApi(() => api.job(id), [id]);
  const [params, setParams] = useSearchParams();
  const tab: Tab = isTab(params.get('tab')) ? (params.get('tab') as Tab) : 'gaps';
  const [opened, setOpened] = useState<Set<Tab>>(() => new Set([tab]));

  const open = (next: Tab) => {
    setOpened((o) => new Set(o).add(next));
    setParams(next === 'gaps' ? {} : { tab: next }, { replace: true });
  };

  if (job.state.status === 'loading') {
    return (
      <div className={ui.page}>
        <PageHead title={t('prep.title')} />
        <Loading />
      </div>
    );
  }
  if (job.state.status === 'error') {
    const notFound = errorCode(job.state.error) === 'JOB_NOT_FOUND';
    return (
      <div className={ui.page}>
        <PageHead title={t('prep.title')} back={{ to: paths.jobs, label: t('job.backToList') }} />
        {notFound ? <Empty title={t('prep.notFound')} /> : <ErrorPanel error={job.state.error} onRetry={job.reload} />}
      </div>
    );
  }

  const data = job.state.data;
  return (
    <div className={ui.page}>
      <PageHead
        title={`${t('prep.title')} · ${data.title}`}
        lead={t('prep.lead')}
        back={{ to: generatePath(paths.jobDetail, { jobId: String(data.id) }), label: data.title }}
        extra={
          <div className={s.jobHeadTop} style={{ marginTop: 10 }}>
            <JobMeta company={data.company_name} location={data.location} employmentType={data.employment_type} minExperienceYears={data.min_experience_years} />
          </div>
        }
      />

      <div className={ui.tabs} role="tablist">
        {TABS.map(({ id: tabId, icon: Icon }) => (
          <button
            key={tabId}
            id={`prep-tab-${tabId}`}
            type="button"
            role="tab"
            className={ui.tab}
            aria-selected={tab === tabId}
            aria-controls={`prep-panel-${tabId}`}
            onClick={() => open(tabId)}
          >
            <Icon width={16} height={16} />
            {t(`prep.tab.${tabId}`)}
          </button>
        ))}
      </div>

      {TABS.filter((x) => opened.has(x.id) || x.id === tab).map(({ id: tabId }) => (
        <div key={tabId} id={`prep-panel-${tabId}`} role="tabpanel" aria-labelledby={`prep-tab-${tabId}`} hidden={tab !== tabId}>
          {tabId === 'gaps' && <Gaps jobId={data.id} />}
          {tabId === 'interview' && <Interview jobId={data.id} />}
          {tabId === 'review' && <Review />}
        </div>
      ))}
    </div>
  );
}

function Gaps({ jobId }: { jobId: number }) {
  const { state, reload } = useApi(() => api.roadmap(jobId), [jobId]);
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <PrepError error={state.error} onRetry={reload} />;
  return <Roadmap data={state.data} />;
}

function PrepError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  // The job closed or its deadline passed while the page was open
  if (errorCode(error) === 'JOB_NOT_FOUND') return <Empty title={t('prep.notFound')} />;
  return <SeekerGate error={error} onRetry={onRetry} />;
}

function Roadmap({ data }: { data: RoadmapOut }) {
  if (data.gaps.length === 0) {
    return (
      <div className={ui.stack}>
        <AiNotice notice={data.notice} method={data.method} />
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

  return (
    <div className={ui.stack}>
      <AiNotice notice={data.notice} method={data.method} />
      {data.limited && <p className={ui.caption}>{t('common.limited')}</p>}
      <div className={s.prepGrid}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>
              {t('prep.gaps.title')}
              <span className={ui.count}>{data.gaps.length}</span>
            </h2>
          </div>
          <ul className={ui.rows}>
            {data.gaps.map((g) => (
              <li key={`${g.kind}-${g.name}`} className={ui.gapRow}>
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
            {data.steps.map((step) => (
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
                        {step.activities.map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h3 className={ui.sectionTitle}>{t('prep.roadmap.resources')}</h3>
                      {step.resources.length === 0 ? (
                        <p className={ui.caption}>{t('prep.roadmap.noResources')}</p>
                      ) : (
                        <div className={ui.stack} style={{ gap: 6 }}>
                          {step.resources.map((r) => (
                            <a key={r.url} className={s.resource} href={r.url} target="_blank" rel="noreferrer">
                              {r.title}
                              <ExternalIcon width={14} height={14} />
                            </a>
                          ))}
                        </div>
                      )}
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

function Interview({ jobId }: { jobId: number }) {
  const { state, reload } = useApi(() => api.interviewQuestions(jobId), [jobId]);
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <PrepError error={state.error} onRetry={reload} />;
  return <Questions data={state.data} />;
}

function Questions({ data }: { data: InterviewOut }) {
  return (
    <div className={ui.stack}>
      <AiNotice notice={data.notice} method={data.method} />
      {data.limited && <p className={ui.caption}>{t('common.limited')}</p>}
      <div>
        <h2 className={ui.panelTitle}>{t('prep.q.title', { n: data.questions.length })}</h2>
        <p className={ui.caption} style={{ margin: '4px 0 14px' }}>
          {t('prep.q.lead')}
        </p>
        {data.questions.map((q, i) => (
          <article key={i} className={s.question}>
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
                  {q.answer_tips.map((tip, j) => (
                    <li key={j}>{tip}</li>
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

/** The CV self-check is per CV version, not per job (D25): the newest version is checked. */
function Review() {
  const { state, reload } = useApi(async () => api.reviewCv((await api.myCv()).id), []);
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <SeekerGate error={state.error} onRetry={reload} />;
  return (
    <div className={ui.stack}>
      <div>
        <h2 className={ui.panelTitle}>{t('prep.review.title')}</h2>
        <p className={ui.caption} style={{ margin: '4px 0 0' }}>
          {t('prep.review.lead')}
        </p>
      </div>
      <ReviewResult review={state.data} />
    </div>
  );
}
