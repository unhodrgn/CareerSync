import { isRouteErrorResponse, Link, useRouteError } from 'react-router';
import { AlertIcon, RefreshIcon } from '@/components/common/icons';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

/**
 * A render error inside a route (errorElement), shown as the app's failed state instead of React Router's raw
 * "Unexpected Application Error!" page. `inShell`: inside the content panel, so the rail and header stay; otherwise
 * on its own gray ground (the shell itself failed, or an auth page). The error goes to the console for developers.
 */
export default function RouteError({ inShell = false }: { inShell?: boolean }) {
  const error = useRouteError();
  console.error(error);
  const notFound = isRouteErrorResponse(error) && error.status === 404;

  const content = (
    <section className={cx(ui.panel, !inShell && ui.standaloneCard)}>
      <div className={ui.empty} role="alert">
        <span className={ui.emptyIcon} data-tone="error" aria-hidden="true">
          <AlertIcon width={24} height={24} />
        </span>
        <h1 className={ui.emptyTitle}>{notFound ? t('page.public.notFound.title') : t('error.render.title')}</h1>
        {!notFound && <p className={ui.emptyBody}>{t('error.render.body')}</p>}
        <div className={ui.actions}>
          {!notFound && (
            <button type="button" className={cx(ui.btn, ui.primary, ui.small)} onClick={() => window.location.reload()}>
              <RefreshIcon width={15} height={15} />
              {t('common.retry')}
            </button>
          )}
          <Link to={paths.home} className={cx(ui.btn, ui.secondary, ui.small)}>
            {t('notFound.home')}
          </Link>
        </div>
      </div>
    </section>
  );

  return inShell ? (
    <div className={ui.page}>{content}</div>
  ) : (
    <main className={ui.standalone} data-theme="app">
      {content}
    </main>
  );
}
