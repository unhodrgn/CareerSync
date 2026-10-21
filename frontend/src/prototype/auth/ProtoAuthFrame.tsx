import type { ReactNode } from 'react';
import { Link } from 'react-router';
import frame from '@/components/common/AuthFrame.module.css';
import type { FrameTone } from '@/components/common/AuthFrame';
import { LogoMark } from '@/components/common/icons';
import { t, type MessageKey } from '@/i18n';
import { pp } from '../paths';

// Same markup and styles as components/common/AuthFrame, but the logo stays inside the prototype.
const FIELD: Record<FrameTone, { title: MessageKey; points: MessageKey[] }> = {
  seeker: { title: 'auth.field.seekerTitle', points: ['auth.field.seekerPoint1', 'auth.field.seekerPoint2', 'auth.field.seekerPoint3'] },
  company: { title: 'auth.field.companyTitle', points: ['auth.field.companyPoint1', 'auth.field.companyPoint2', 'auth.field.companyPoint3'] },
  hub: { title: 'auth.field.hubTitle', points: [] },
};

export default function ProtoAuthFrame({ tone, headerEnd, children }: { tone: FrameTone; headerEnd?: ReactNode; children: ReactNode }) {
  const field = FIELD[tone];
  return (
    <div className={frame.page} data-tone={tone}>
      <header className={frame.header}>
        <Link to={pp.guest.jobs} className={frame.brand} aria-label={t('auth.home')}>
          <LogoMark />
          <span className={frame.brandName}>{t('app.name')}</span>
        </Link>
        <div className={frame.headerEnd}>
          <span className={frame.tagline}>{t('auth.tagline')}</span>
          {headerEnd}
        </div>
      </header>
      <div className={frame.body}>
        <aside className={frame.field}>
          <div className={frame.fieldInner}>
            <p className={frame.fieldTitle}>{t(field.title)}</p>
            {tone === 'hub' ? (
              <ul className={frame.hubRows}>
                <li className={frame.hubRow}>
                  <span className={frame.dotSeeker} />
                  {t('auth.field.hubSeeker')}
                </li>
                <li className={frame.hubRow}>
                  <span className={frame.dotCompany} />
                  {t('auth.field.hubCompany')}
                </li>
                <li className={frame.hubNote}>{t('auth.field.hubNote')}</li>
              </ul>
            ) : (
              <ol className={frame.points}>
                {field.points.map((key, i) => (
                  <li key={key} className={frame.point}>
                    <span className={frame.pointIndex}>{i + 1}</span>
                    {t(key)}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </aside>
        <main className={frame.main}>{children}</main>
      </div>
    </div>
  );
}
