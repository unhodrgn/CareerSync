import { useEffect } from 'react';
import { useLocation } from 'react-router';

// The pathname the app showed last, shared by every layout: moving between shells (로그인 → the seeker shell) still
// counts as navigation, while the app's first render does not move focus.
let shownPath: string | null = null;
// The running follow-up of the last navigation. Only the next navigation stops it, not an unmount: a shell can remount
// on the same page (a seeker page → 공고 목록 swaps SeekerLayout for BrowseLayout; RequireRole after login)
let stopPending: (() => void) | null = null;

// How long a page may take to show its H1 after a navigation before focus is left where it is
const WAIT_MS = 10_000;

/**
 * Focus after client-side navigation (a pathname change, not the first load and not a query-string change such as a
 * search or a filter): the new page's H1 gets focus, so screen readers read the page name and the next Tab starts in
 * the page. Without an H1 yet — still loading (a `Loading` skeleton, marked `data-loading`) or a page without one —
 * focus goes to <main>, and moves on to the H1 when it appears, as long as the user has not moved focus. The browser
 * draws the focus ring only when the navigation came from the keyboard (:focus-visible); scrolling is left alone.
 */
export function useRouteFocus(): void {
  const { pathname } = useLocation();
  useEffect(() => {
    const first = shownPath === null;
    const changed = shownPath !== pathname;
    shownPath = pathname;
    if (first || !changed) return;
    stopPending?.();
    stopPending = focusPage();
  }, [pathname]);
}

function focusPage(): () => void {
  // Looked up each time: a remounted shell replaces <main>
  const mainEl = () => document.querySelector<HTMLElement>('main');
  const scope = () => mainEl() ?? document.body;
  const place = (el: HTMLElement) => {
    if (!el.hasAttribute('tabindex')) el.tabIndex = -1;
    el.focus({ preventScroll: true });
  };
  // The page's own H1, once it is no longer loading
  const heading = () => (scope().querySelector('[data-loading]') ? null : scope().querySelector<HTMLElement>('h1'));
  // Focus is still where navigation left it: on <main>, or dropped to <body> when its element was replaced
  const unmoved = () => {
    const active = document.activeElement;
    return !active || active === document.body || active === mainEl();
  };

  const h1 = heading();
  const main = mainEl();
  if (h1) place(h1);
  else if (main) place(main);

  // The H1 may come later (data loading) or be replaced (a placeholder title): follow it until the user acts
  const observer = new MutationObserver(() => {
    const next = heading();
    if (next && next !== document.activeElement && unmoved()) place(next);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  const timer = window.setTimeout(stop, WAIT_MS);
  document.addEventListener('keydown', stop, true);
  document.addEventListener('pointerdown', stop, true);
  function stop() {
    observer.disconnect();
    window.clearTimeout(timer);
    document.removeEventListener('keydown', stop, true);
    document.removeEventListener('pointerdown', stop, true);
  }
  return stop;
}
