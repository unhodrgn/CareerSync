import { CategoryTag, ImportanceTag } from '@/components/common/Labels';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t, type MessageKey } from '@/i18n';
import type { CriteriaView, SeekerCriteriaSetOut } from '@/types/criteria';
import s from './seeker.module.css';

function isSeekerView(view: CriteriaView): view is SeekerCriteriaSetOut {
  return view.items.length > 0 && 'importance' in view.items[0] && !('weight' in view.items[0]);
}

/**
 * A job's criteria on the public job page. What shows follows what the API returned for this viewer: a guest gets
 * names only (D35), a signed-in seeker name + category + importance (D30). The owner company's full rows carry
 * weights; this page never shows them, so the owner sees names only here.
 */
export default function CriteriaPanel({ view }: { view: CriteriaView }) {
  const seeker = isSeekerView(view);
  const lead: MessageKey = seeker ? 'job.criteriaLead' : 'job.criteriaGuestLead';
  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      <div>
        <h2 className={s.asideTitle}>{t('job.criteria')}</h2>
        <p className={ui.caption}>{t(lead)}</p>
      </div>
      {view.items.length === 0 ? (
        <p className={ui.caption}>{t('job.criteriaNone')}</p>
      ) : (
        <ul className={ui.rows}>
          {seeker
            ? view.items.map((c) => (
                <li key={c.name} className={ui.row}>
                  <span className={ui.rowName}>
                    <span className={ui.dot} />
                    <span className={ui.truncate}>{c.name}</span>
                  </span>
                  <span className={ui.rowEnd}>
                    <CategoryTag category={c.category} />
                    <ImportanceTag level={c.importance} />
                  </span>
                </li>
              ))
            : view.items.map((c) => (
                <li key={c.name} className={ui.row}>
                  <span className={ui.rowName}>
                    <span className={ui.dot} />
                    <span className={ui.truncate}>{c.name}</span>
                  </span>
                </li>
              ))}
        </ul>
      )}
    </section>
  );
}
