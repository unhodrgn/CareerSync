import { Link } from 'react-router';
import { SearchIcon } from '@/components/common/icons';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

/** Unknown path: outside every shell, so it draws its own gray ground with one centered card. */
export default function NotFound() {
  return (
    <main className={ui.standalone} data-theme="app">
      <section className={cx(ui.panel, ui.standaloneCard)}>
        <div className={ui.empty}>
          <span className={ui.emptyIcon} aria-hidden="true">
            <SearchIcon width={24} height={24} />
          </span>
          <h1 className={ui.emptyTitle}>{t('page.public.notFound.title')}</h1>
          <Link to={paths.home} className={cx(ui.btn, ui.secondary)}>
            {t('notFound.home')}
          </Link>
        </div>
      </section>
    </main>
  );
}
