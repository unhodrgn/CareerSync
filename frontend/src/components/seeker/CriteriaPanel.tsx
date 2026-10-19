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
 * A job's criteria on the public job page, as a quiet read-only list. What shows follows what the API returned
 * for this viewer: a guest gets names only (D35), a signed-in seeker name + category + importance (D30). The
 * owner company's full rows carry weights; this page never shows them, so the owner sees names only here.
 */
export default function CriteriaPanel({ view }: { view: CriteriaView }) {
  const seeker = isSeekerView(view);
  // The owner company reads its own names here; the caption speaks to seekers and guests only
  const owner = view.items.length > 0 && 'weight' in view.items[0];
  const lead: MessageKey | null = seeker ? 'job.criteriaLead' : owner ? null : 'job.criteriaGuestLead';
  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      <h2 className={s.asideTitle}>{t('job.criteria')}</h2>
      {view.items.length === 0 ? (
        <p className={ui.caption}>{t('job.criteriaNone')}</p>
      ) : (
        <ul className={ui.list}>
          {seeker
            ? view.items.map((c) => (
                <li key={c.name} className={ui.listRow}>
                  <span className={ui.listName}>{c.name}</span>
                  <span className={ui.listEnd}>
                    <CategoryTag category={c.category} quiet />
                    <ImportanceTag level={c.importance} />
                  </span>
                </li>
              ))
            : view.items.map((c) => (
                <li key={c.name} className={ui.listRow}>
                  <span className={ui.listName}>{c.name}</span>
                </li>
              ))}
        </ul>
      )}
      {lead && <p className={ui.caption}>{t(lead)}</p>}
    </section>
  );
}
