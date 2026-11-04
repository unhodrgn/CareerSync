import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { LogoMark } from '@/components/common/icons';
import { t, type MessageKey } from '@/i18n';
import { paths } from '@/routes/paths';
import styles from './AuthFrame.module.css';

/** Field colour: the seeker navy, the employer green, or the hub ink for pages that serve both sides. */
export type FrameTone = 'seeker' | 'company' | 'hub';

const FIELD: Record<FrameTone, { title: MessageKey; points: MessageKey[] }> = {
  seeker: {
    title: 'auth.field.seekerTitle',
    points: ['auth.field.seekerPoint1', 'auth.field.seekerPoint2', 'auth.field.seekerPoint3'],
  },
  company: {
    title: 'auth.field.companyTitle',
    points: ['auth.field.companyPoint1', 'auth.field.companyPoint2', 'auth.field.companyPoint3'],
  },
  hub: { title: 'auth.field.hubTitle', points: [] },
};

/**
 * Shell of the login, register and consent pages, in the landing's world: the audience field on the left
 * (its colour follows `tone`), the form card on the off-white ground on the right.
 */
export default function AuthFrame({ tone, headerEnd, children }: { tone: FrameTone; headerEnd?: ReactNode; children: ReactNode }) {
  const field = FIELD[tone];
  return (
    <div className={styles.page} data-tone={tone}>
      <header className={styles.header}>
        <Link to={paths.home} className={styles.brand} aria-label={t('auth.home')}>
          <LogoMark />
          <span className={styles.brandName}>{t('app.name')}</span>
        </Link>
        <div className={styles.headerEnd}>
          <span className={styles.tagline}>{t('auth.tagline')}</span>
          {headerEnd}
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.field}>
          <div className={styles.fieldInner}>
            <p className={styles.fieldTitle}>{t(field.title)}</p>
            {tone === 'hub' ? (
              <ul className={styles.hubRows}>
                <li className={styles.hubRow}>
                  <span className={styles.dotSeeker} />
                  {t('auth.field.hubSeeker')}
                </li>
                <li className={styles.hubRow}>
                  <span className={styles.dotCompany} />
                  {t('auth.field.hubCompany')}
                </li>
                <li className={styles.hubNote}>{t('auth.field.hubNote')}</li>
              </ul>
            ) : (
              <ol className={styles.points}>
                {field.points.map((key, i) => (
                  <li key={key} className={styles.point}>
                    <span className={styles.pointIndex}>{i + 1}</span>
                    {t(key)}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </aside>
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}
