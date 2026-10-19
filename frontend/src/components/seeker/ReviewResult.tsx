import { AiNotice } from '@/components/common/AiNotice';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { CvReviewItem, CvReviewOut } from '@/types/cv';
import s from './seeker.module.css';

function ReviewList({ items }: { items: CvReviewItem[] }) {
  if (items.length === 0) return <p className={ui.caption}>{t('prep.review.none')}</p>;
  // The server already lists the affects-scoring findings first; keep that order stable
  const sorted = [...items].sort((a, b) => Number(b.affects_scoring) - Number(a.affects_scoring));
  return (
    <div>
      {sorted.map((x, i) => (
        <div key={i} className={s.reviewItem}>
          <h4 className={s.reviewTitle}>
            {x.title}
            {x.affects_scoring && <span className={cx(ui.tag, ui.tagTone)}>{t('prep.review.affects')}</span>}
          </h4>
          <p className={ui.body}>{x.detail}</p>
          {x.cv_quote && <p className={ui.quote}>{x.cv_quote}</p>}
        </div>
      ))}
    </div>
  );
}

/** CV self-check result (D25): strengths and improvements, no score. Used on 내 이력서 and on the prep page. */
export default function ReviewResult({ review }: { review: CvReviewOut }) {
  return (
    <div className={ui.stack}>
      <AiNotice notice={review.notice} method={review.method} />
      {review.limited && <p className={ui.caption}>{t('common.limited')}</p>}
      <div className={s.reviewCols}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h3 className={ui.panelTitle}>
              {t('prep.review.strengths')}
              <span className={ui.count}>{review.strengths.length}</span>
            </h3>
          </div>
          <ReviewList items={review.strengths} />
        </section>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h3 className={ui.panelTitle}>
              {t('prep.review.improvements')}
              <span className={ui.count}>{review.improvements.length}</span>
            </h3>
          </div>
          <ReviewList items={review.improvements} />
          <p className={ui.caption} style={{ marginTop: 16 }}>
            {t('prep.review.affectsNote')}
          </p>
        </section>
      </div>
    </div>
  );
}
