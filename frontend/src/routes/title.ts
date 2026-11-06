import { useEffect } from 'react';
import { useMatches, type createBrowserRouter } from 'react-router';
import { t, type MessageKey } from '@/i18n';

// Document titles. Every route names its page with an i18n key in `handle.title` (router.tsx); the title is
// "{page} – CareerSync", and a page with a subject (a job, a company, an applicant) puts it first once loaded:
// "{subject} – {page} – CareerSync". The landing has no handle and keeps the bare app name. A title change is never
// announced and never moves focus; focus after navigation is useRouteFocus's job.

/** What a route carries in `handle`. */
export interface RouteHandle {
  title?: MessageKey;
}

const SEPARATOR = ' – ';

/** The title key of the deepest matched route that has one, from the matched routes' handles (outermost first). */
function titleKeyOf(handles: readonly unknown[]): MessageKey | undefined {
  for (let i = handles.length - 1; i >= 0; i--) {
    const handle = handles[i] as RouteHandle | undefined;
    if (handle?.title) return handle.title;
  }
  return undefined;
}

/** The parts that are set, then the app name, joined by the separator. */
function compose(...parts: (string | null | undefined)[]): string {
  return [...parts.map((p) => p?.trim()).filter((p): p is string => !!p), t('app.name')].join(SEPARATOR);
}

/**
 * Keeps the static route title in sync with the router: at start and whenever the pathname changes. A change of the
 * query string alone (search, filters) keeps the title, so a subject title set by the page is not lost.
 */
export function startTitleSync(router: ReturnType<typeof createBrowserRouter>): void {
  let titledPath: string | null = null;
  const sync = (state: typeof router.state) => {
    if (state.location.pathname === titledPath) return;
    titledPath = state.location.pathname;
    const key = titleKeyOf(state.matches.map((m) => m.route.handle));
    document.title = compose(key ? t(key) : null);
  };
  sync(router.state);
  router.subscribe(sync);
}

/**
 * Puts the page's subject in front of its route title once it is known; until then (and with no subject) the static
 * route title stays. `titleKey` replaces the route's page name next to the subject (지원자 관리 → 지원자 상세 while an
 * applicant is open). On unmount without navigation the static title comes back.
 */
export function useDocumentTitle(subject: string | null | undefined, titleKey?: MessageKey): void {
  const routeKey = titleKeyOf(useMatches().map((m) => m.handle));
  const routeTitle = routeKey ? t(routeKey) : null;
  const pageTitle = titleKey ? t(titleKey) : routeTitle;
  const name = subject?.trim() || null;

  useEffect(() => {
    if (!name) return;
    const path = window.location.pathname;
    document.title = compose(name, pageTitle);
    return () => {
      // Navigating away: the router has already set the next page's title, so leave it
      if (window.location.pathname === path) document.title = compose(routeTitle);
    };
  }, [name, pageTitle, routeTitle]);
}
