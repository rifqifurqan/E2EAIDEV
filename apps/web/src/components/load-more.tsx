"use client";

import { useI18n } from "@/i18n/context";

/** Shared "load more" control for cursor-paginated lists; renders nothing when the list is exhausted. */
export function LoadMore({
  hasMore,
  busy,
  failed,
  onLoadMore,
}: {
  hasMore: boolean;
  busy: boolean;
  failed: boolean;
  onLoadMore: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="mt-2">
      {failed ? (
        <p role="alert" className="mb-1 text-sm text-red-700">
          {t.common.loadMoreFailed}
        </p>
      ) : null}
      {hasMore ? (
        <button
          type="button"
          disabled={busy}
          onClick={onLoadMore}
          className="rounded border border-gray-400 px-3 py-1 text-sm text-gray-700 disabled:opacity-50"
        >
          {t.common.loadMore}
        </button>
      ) : null}
    </div>
  );
}
