"use client";

import { useCallback, useState } from "react";

interface PageState<T> {
  base: readonly T[] | undefined;
  extra: T[];
  /** undefined = not started (use the base cursor); null = exhausted. */
  cursor: string | null | undefined;
}

/**
 * Cursor "load more" on top of an already loaded first page. When the base list changes
 * (a reload), appended pages are dropped so the view never mixes stale and fresh rows.
 */
export function useLoadMore<T>(
  base: readonly T[] | undefined,
  baseCursor: string | null | undefined,
  fetchPage: (cursor: string) => Promise<{ items: T[]; next_cursor: string | null }>,
) {
  const [state, setState] = useState<PageState<T>>({ base, extra: [], cursor: undefined });
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const current: PageState<T> = state.base === base ? state : { base, extra: [], cursor: undefined };
  const cursor = current.cursor === undefined ? (baseCursor ?? null) : current.cursor;

  const loadMore = useCallback(async () => {
    if (cursor === null) return;
    setFailed(false);
    setBusy(true);
    try {
      const page = await fetchPage(cursor);
      setState({ base, extra: [...current.extra, ...page.items], cursor: page.next_cursor });
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursor, base, current.extra, fetchPage]);

  return {
    items: [...(base ?? []), ...current.extra],
    hasMore: cursor !== null,
    busy,
    failed,
    loadMore,
  };
}
