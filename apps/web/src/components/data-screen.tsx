"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type DueReview } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { WhyItMattersPanel } from "./why-it-matters-panel";

const INTERVALS = [30, 90, 180, 365];

function ReviewRow({ review, onDone }: { review: DueReview; onDone: () => void }) {
  const { t } = useI18n();
  const [days, setDays] = useState(180);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const selectId = `next-review-${review.document_id}`;

  async function markReviewed() {
    setFailed(false);
    setBusy(true);
    try {
      await api.markReviewed(review.document_id, days);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      onDone();
    }
  }

  return (
    <li className="rounded border border-gray-200 p-2">
      <span className="mr-2">{review.title}</span>
      <span className="font-mono text-xs text-gray-500">{`${review.overdue_days} ${t.data.overdueDays}`}</span>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label htmlFor={selectId} className="text-xs">
          <span className="mr-1">{t.data.nextReviewIn}</span>
          <select
            id={selectId}
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            className="rounded border border-gray-300 px-1 py-0.5 text-xs"
          >
            {INTERVALS.map((value) => (
              <option key={value} value={value}>{`${value} ${t.data.days}`}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={markReviewed}
          className="rounded border border-green-400 px-2 py-0.5 text-xs text-green-700 disabled:opacity-50"
        >
          {t.data.markReviewed}
        </button>
      </div>
      {failed ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {t.data.reviewFailed}
        </p>
      ) : null}
    </li>
  );
}

export function DataScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const state = useAdminData(() => api.listDueReviews(), reloadKey);

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.nav.data}</h1>
      <h2 className="mb-3 text-lg font-semibold">{t.data.title}</h2>
      {state.kind === "loading" ? <p>{t.data.loading}</p> : null}
      {state.kind === "forbidden" ? (
        <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
          {t.data.signIn}
        </p>
      ) : null}
      {state.kind === "error" ? (
        <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
          {t.data.loadFailed}
        </p>
      ) : null}
      {state.kind === "ready" ? (
        state.data.reviews.length === 0 ? (
          <p className="text-sm text-gray-500">{t.data.noItems}</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {state.data.reviews.map((review) => (
              <ReviewRow key={review.document_id} review={review} onDone={() => setReloadKey((key) => key + 1)} />
            ))}
          </ul>
        )
      ) : null}
      <WhyItMattersPanel stage="data" />
    </section>
  );
}
