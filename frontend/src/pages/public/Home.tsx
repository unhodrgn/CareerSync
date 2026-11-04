import { useState, type KeyboardEvent, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import {
  AlertIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  CornerDownIcon,
  CornerDownLeftIcon,
  DocumentIcon,
  LogoMark,
  ShieldLockIcon,
  SlidersIcon,
} from '@/components/common/icons';
import { t, type MessageKey } from '@/i18n';
import { paths } from '@/routes/paths';
import styles from './Home.module.css';

// Synthetic example built on the seed job 클라우드랩 · 데이터 엔지니어 (scripts/seed.py), labeled 예시.
// Seekers see criteria names, the band and skills their CV lacks, never scores or "met" verdicts (docs/DECISIONS.md
// D1, D21); companies see named applicants ranked with evidence. Talent anonymity is stated in the trust note only.
type CriterionId = 'python' | 'pipeline' | 'aws' | 'major';

const CRITERIA: { id: CriterionId; category: MessageKey }[] = [
  { id: 'python', category: 'landing.category.skill' },
  { id: 'pipeline', category: 'landing.category.experience' },
  { id: 'aws', category: 'landing.category.skill' },
  { id: 'major', category: 'landing.category.education' },
];

// The criterion whose skill the example CV lacks (D21); Airflow, named only in the JD, sits in the card footer
const GAP: CriterionId = 'aws';

const APPLICANTS: { key: 'a' | 'b'; met: Record<CriterionId, boolean> }[] = [
  { key: 'a', met: { python: true, pipeline: true, aws: true, major: true } },
  { key: 'b', met: { python: true, pipeline: true, aws: false, major: true } },
];

type Role = 'seeker' | 'company';
const registerAs = (role: Role) => `${paths.register}?role=${role}`;

export default function Home() {
  const navigate = useNavigate();
  // Hover or focus previews a criterion; a click pins it until it is clicked again or Escape is pressed
  const [hovered, setHovered] = useState<CriterionId | null>(null);
  const [pinned, setPinned] = useState<CriterionId | null>(null);
  const active = hovered ?? pinned;

  const trail = (id: CriterionId) => ({
    'data-lit': active === id || undefined,
    onMouseEnter: () => setHovered(id),
    onMouseLeave: () => setHovered(null),
    onClick: (e: MouseEvent) => {
      e.stopPropagation();
      setPinned((p) => (p === id ? null : id));
    },
  });
  const focusable = (id: CriterionId) => ({
    'aria-pressed': pinned === id,
    onFocus: () => setHovered(id),
    onBlur: () => setHovered(null),
    onKeyDown: (e: KeyboardEvent) => e.key === 'Escape' && setPinned(null),
  });

  // A click on the panel's open area signs up for that side; links, buttons and the example cards keep their own behavior
  const panelClick = (role: Role) => (e: MouseEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest('a, button, [data-stop-panel]')) return;
    navigate(registerAs(role));
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to={paths.home} className={styles.brand} aria-label={t('landing.home')}>
          <LogoMark />
          <span className={styles.brandName}>{t('app.name')}</span>
        </Link>
        <div className={styles.headerEnd}>
          <span className={styles.tagline}>{t('landing.tagline')}</span>
          <Link to={paths.login} className={`${styles.press} ${styles.loginButton}`}>
            {t('landing.login')}
          </Link>
        </div>
      </header>

      <main className={styles.split} data-active={active ?? undefined}>
        {/* Seeker panel */}
        <section
          className={`${styles.panel} ${styles.seeker}`}
          aria-labelledby="landing-seeker-title"
          onClick={panelClick('seeker')}
        >
          <span className={styles.numeral} aria-hidden="true">
            01
          </span>
          <div className={styles.zoneTop}>
            <div>
              <p className={styles.roleRow}>
                <span className={styles.roleLabel}>
                  <span className={styles.roleDot} />
                  {t('landing.seeker.audience')}
                </span>
                <span className={styles.panelHint}>{t('landing.panelHint')}</span>
              </p>
              <h1 id="landing-seeker-title" className={styles.title}>
                {t('landing.seeker.title')}
              </h1>
              <p className={styles.lead}>{t('landing.seeker.lead')}</p>
            </div>
            <div className={styles.actions}>
              <Link to={registerAs('seeker')} className={`${styles.press} ${styles.primary}`}>
                {t('landing.seeker.cta')}
                <ArrowRightIcon width={16} height={16} />
              </Link>
              <Link to={paths.jobs} className={styles.textLink}>
                {t('landing.seeker.browse')}
              </Link>
            </div>
          </div>

          <div className={styles.zoneTrail}>
            <div className={styles.inputChip}>
              <span className={styles.inputIcon}>
                <DocumentIcon width={16} height={16} />
              </span>
              <span className={styles.inputText}>
                <span className={styles.inputHead}>
                  <span className={styles.inputTitle}>{t('landing.seeker.input.title')}</span>
                  <span className={styles.inputMeta}>{t('landing.seeker.input.meta')}</span>
                </span>
                <span className={styles.inputDetail}>{t('landing.seeker.input.detail')}</span>
              </span>
            </div>
            <span className={styles.feed}>
              {t('landing.seeker.input.link')}
              <span className={styles.feedLine} />
              <ArrowRightIcon width={16} height={16} />
            </span>
          </div>

          <div className={styles.zoneResult}>
            <p className={styles.resultHead}>
              <span className={styles.resultLabel}>
                <CornerDownIcon width={14} height={14} />
                {t('landing.seeker.outcome')}
              </span>
              <span className={styles.resultNote}>{t('landing.seeker.outcomeNote')}</span>
            </p>
            <figure className={styles.card} data-stop-panel aria-label={t('landing.seeker.card.label')}>
              <div className={styles.cardHead}>
                <span>
                  <span className={styles.cardMeta}>
                    <strong>{t('landing.job.company')}</strong>
                    <span>·</span>
                    <span>
                      {t('landing.job.location')} · {t('landing.job.employment')}
                    </span>
                    <span className={styles.exampleTag}>{t('landing.example')}</span>
                  </span>
                  <span className={styles.cardTitle}>{t('landing.job.title')}</span>
                </span>
                <span className={styles.band}>
                  <span className={styles.bandDot} />
                  {t('landing.seeker.card.band')}
                </span>
              </div>
              <ul className={styles.rows}>
                {CRITERIA.map((c) => (
                  <li
                    key={c.id}
                    className={styles.seekerRow}
                    data-gap={c.id === GAP || undefined}
                    data-dim-target
                    {...trail(c.id)}
                  >
                    <span className={styles.rowName}>
                      {c.id === GAP ? (
                        <AlertIcon className={styles.rowIcon} width={15} height={15} />
                      ) : (
                        <span className={styles.rowMark} />
                      )}
                      <span className={styles.truncate}>{t(`landing.criterion.${c.id}`)}</span>
                    </span>
                    <span className={styles.rowBadge}>
                      {c.id === GAP ? t('landing.seeker.card.missing') : t('landing.seeker.card.inBand')}
                    </span>
                  </li>
                ))}
              </ul>
              <figcaption className={styles.cardFoot}>
                <span>{t('landing.seeker.card.jdGap')}</span>
                <strong className={`${styles.seekerStrong} ${styles.withIcon}`}>
                  {t('landing.seeker.card.roadmap')}
                  <ArrowRightIcon width={12} height={12} />
                </strong>
              </figcaption>
            </figure>
          </div>
        </section>

        {/* Shared criteria spine */}
        <aside className={styles.spine} aria-labelledby="landing-spine-title">
          <span className={styles.axis} aria-hidden="true" />
          <div className={styles.identity}>
            <p className={styles.pillRow}>
              <span className={styles.pill}>
                <span className={styles.pillDotSeeker} />
                {t('landing.spine.label')}
                <span className={styles.pillDotEmployer} />
              </span>
            </p>
            <div>
              <h2 id="landing-spine-title" className={styles.identityTitle}>
                {t('landing.spine.title')}
              </h2>
              <p className={styles.identityLead}>{t('landing.spine.lead')}</p>
            </div>
            <p className={styles.directions}>
              <span className={`${styles.toSeeker} ${styles.withIcon}`}>
                <ArrowLeftIcon width={12} height={12} />
                {t('landing.spine.toSeeker')}
              </span>
              <span className={`${styles.toEmployer} ${styles.withIcon}`}>
                {t('landing.spine.toEmployer')}
                <ArrowRightIcon width={12} height={12} />
              </span>
            </p>
          </div>

          <div className={styles.hub}>
            <span className={styles.tickSeeker} aria-hidden="true" />
            <span className={styles.tickEmployer} aria-hidden="true" />
            <p className={styles.hubRow}>
              <span className={styles.hubSeeker}>
                {t('landing.spine.hub.resume')}
                <ArrowRightIcon width={14} height={14} />
              </span>
              <span className={styles.hubShared}>{t('landing.spine.hub.shared')}</span>
              <span className={styles.hubEmployer}>
                <ArrowLeftIcon width={14} height={14} />
                {t('landing.spine.hub.criteria')}
              </span>
            </p>
            <p className={styles.hubCaption}>{t('landing.spine.hub.caption')}</p>
          </div>

          <div className={styles.zoneResult}>
            <p className={`${styles.resultHead} ${styles.listHead}`}>
              <span className={styles.listTitle}>{t('landing.spine.listTitle')}</span>
              <span className={styles.listHint}>{t('landing.spine.listHint')}</span>
            </p>
            <div className={styles.rubric}>
              <div className={styles.rubricHead}>
                <span>
                  <span className={styles.rubricCaption}>{t('landing.spine.rubric')}</span>
                  <span className={styles.rubricTitle}>{t('landing.job.title')}</span>
                </span>
                <span className={styles.countBadge}>{t('landing.spine.count')}</span>
              </div>
              <ol className={styles.rows}>
                {CRITERIA.map((c, i) => (
                  <li key={c.id} className={styles.critItem}>
                    <button
                      type="button"
                      className={styles.critButton}
                      data-gap={c.id === GAP || undefined}
                      data-dim-target
                      {...trail(c.id)}
                      {...focusable(c.id)}
                    >
                      <span className={styles.wireSeeker} aria-hidden="true" />
                      <span className={styles.truncate}>
                        {i + 1}. {t(`landing.criterion.${c.id}`)}
                      </span>
                      <span className={styles.categoryTag}>{t(c.category)}</span>
                      <span className={styles.wireEmployer} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ol>
              <p className={styles.rubricFoot}>
                <span className={`${styles.seekerStrong} ${styles.withIcon}`}>
                  <ArrowLeftIcon width={12} height={12} />
                  {t('landing.spine.footSeeker')}
                </span>
                <span className={`${styles.employerStrong} ${styles.withIcon}`}>
                  {t('landing.spine.footEmployer')}
                  <ArrowRightIcon width={12} height={12} />
                </span>
              </p>
            </div>
          </div>
        </aside>

        {/* Employer panel */}
        <section
          className={`${styles.panel} ${styles.employer}`}
          aria-labelledby="landing-employer-title"
          onClick={panelClick('company')}
        >
          <span className={styles.numeral} aria-hidden="true">
            02
          </span>
          <div className={styles.zoneTop}>
            <div>
              <p className={styles.roleRow}>
                <span className={styles.roleLabel}>
                  <span className={styles.roleDot} />
                  {t('landing.employer.audience')}
                </span>
                <span className={styles.panelHint}>{t('landing.panelHint')}</span>
              </p>
              <h2 id="landing-employer-title" className={styles.title}>
                {t('landing.employer.title')}
              </h2>
              <p className={styles.lead}>{t('landing.employer.lead')}</p>
            </div>
            <div className={styles.actions}>
              <Link to={registerAs('company')} className={`${styles.press} ${styles.primary}`}>
                {t('landing.employer.cta')}
                <ArrowRightIcon width={16} height={16} />
              </Link>
            </div>
          </div>

          <div className={styles.zoneTrail}>
            <span className={styles.feed}>
              <ArrowLeftIcon width={16} height={16} />
              <span className={styles.feedLine} />
              {t('landing.employer.input.link')}
            </span>
            <div className={styles.inputChip}>
              <span className={styles.inputIcon}>
                <SlidersIcon width={16} height={16} />
              </span>
              <span className={styles.inputText}>
                <span className={styles.inputHead}>
                  <span className={styles.inputTitle}>{t('landing.employer.input.title')}</span>
                  <span className={styles.inputMeta}>{t('landing.employer.input.meta')}</span>
                </span>
                <span className={styles.inputDetail}>{t('landing.employer.input.detail')}</span>
              </span>
            </div>
          </div>

          <div className={styles.zoneResult}>
            <p className={styles.resultHead}>
              <span className={styles.resultLabel}>
                <CornerDownLeftIcon width={14} height={14} />
                {t('landing.employer.outcome')}
              </span>
              <span className={styles.resultNote}>{t('landing.employer.outcomeNote')}</span>
            </p>
            <figure className={styles.card} data-stop-panel aria-label={t('landing.employer.card.label')}>
              <div className={styles.cardHead}>
                <span>
                  <span className={styles.cardMeta}>
                    <strong className={styles.employerStrong}>{t('landing.job.title')}</strong>
                    <span>·</span>
                    <span>{t('landing.employer.card.context')}</span>
                    <span className={styles.exampleTag}>{t('landing.example')}</span>
                  </span>
                  <span className={styles.cardTitle}>{t('landing.employer.card.title')}</span>
                </span>
                <span className={styles.countTag}>{t('landing.spine.count')}</span>
              </div>

              <p className={styles.tags}>
                {CRITERIA.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={styles.tag}
                    data-dim-target
                    {...trail(c.id)}
                    {...focusable(c.id)}
                  >
                    {t(`landing.criterionShort.${c.id}`)}
                  </button>
                ))}
              </p>

              <ol className={styles.applicants}>
                {APPLICANTS.map((a, rank) => {
                  const met = CRITERIA.filter((c) => a.met[c.id]).length;
                  return (
                    <li key={a.key} className={styles.applicant}>
                      <div className={styles.applicantHead}>
                        <span className={styles.applicantId}>
                          <span className={styles.rank}>{rank + 1}</span>
                          <span className={styles.applicantName}>{t(`landing.applicant.${a.key}.name`)}</span>
                          <span className={styles.metBadge} data-all={met === CRITERIA.length || undefined}>
                            {t('landing.employer.card.met').replace('{n}', String(met))}
                          </span>
                        </span>
                        <span className={styles.squares}>
                          {CRITERIA.map((c) => (
                            <span
                              key={c.id}
                              className={styles.square}
                              data-missing={!a.met[c.id] || undefined}
                              data-dim-target
                              title={t(`landing.criterion.${c.id}`)}
                              {...trail(c.id)}
                            />
                          ))}
                        </span>
                      </div>
                      <p className={styles.note}>
                        <strong className={styles.employerStrong}>{t('landing.employer.card.strength')}</strong>{' '}
                        {t(`landing.applicant.${a.key}.strength`)}
                      </p>
                      <p className={styles.note}>
                        <strong className={met === CRITERIA.length ? styles.mutedStrong : styles.gapStrong}>
                          {t('landing.employer.card.weakness')}
                        </strong>{' '}
                        {t(`landing.applicant.${a.key}.weakness`)}
                      </p>
                    </li>
                  );
                })}
              </ol>

              <figcaption className={styles.cardFoot}>
                <span>{t('landing.employer.card.evidence')}</span>
                <strong className={`${styles.employerStrong} ${styles.withIcon}`}>
                  {t('landing.employer.card.status')}
                  <ArrowRightIcon width={12} height={12} />
                </strong>
              </figcaption>
            </figure>
          </div>
        </section>
      </main>

      <div className={styles.below}>
        <div className={styles.trust}>
          <p className={styles.trustText}>
            <span className={styles.trustIcon}>
              <ShieldLockIcon width={14} height={14} />
            </span>
            <span>
              <strong>{t('landing.trust.title')}</strong> {t('landing.trust.body')}
            </span>
          </p>
          <span className={styles.trustDecision}>{t('landing.trust.decision')}</span>
        </div>
        <footer className={styles.footer}>
          <p>{t('landing.footer.copyright')}</p>
          <p className={styles.legal}>
            <span>{t('landing.footer.terms')}</span>
            <span>{t('landing.footer.privacy')}</span>
          </p>
        </footer>
      </div>
    </div>
  );
}
