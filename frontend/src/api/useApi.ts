import { useCallback, useEffect, useState, type DependencyList } from 'react';

export type ApiState<T> =
  | { status: 'loading'; data: null; error: null }
  | { status: 'ok'; data: T; error: null }
  | { status: 'error'; data: null; error: unknown };

export interface ApiResult<T> {
  state: ApiState<T>;
  /** Load again (shows the loading state). */
  reload: () => void;
  /** Replace the loaded data, e.g. with the response of a write. */
  setData: (data: T) => void;
}

const LOADING = { status: 'loading', data: null, error: null } as const;

/**
 * Loads `load()` on mount and whenever `deps` change. A response that arrives after unmount or after the deps
 * changed is dropped. Pages pass the signed-in user's id in `deps` when the answer depends on who asks.
 */
export function useApi<T>(load: () => Promise<T>, deps: DependencyList): ApiResult<T> {
  const [state, setState] = useState<ApiState<T>>(LOADING);
  const [round, setRound] = useState(0);

  useEffect(() => {
    let current = true;
    setState(LOADING);
    load().then(
      (data) => current && setState({ status: 'ok', data, error: null }),
      (error: unknown) => current && setState({ status: 'error', data: null, error }),
    );
    return () => {
      current = false;
    };
    // `load` is a new closure every render; `deps` says when it changes meaning
  }, [...deps, round]);

  const reload = useCallback(() => setRound((r) => r + 1), []);
  const setData = useCallback((data: T) => setState({ status: 'ok', data, error: null }), []);
  return { state, reload, setData };
}
