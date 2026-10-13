"use client";

import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { WhyItMattersPanel } from "./why-it-matters-panel";

export function DataScreen() {
  const { t } = useI18n();
  const state = useAdminData(() => api.listDueReviews());

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
              <li key={review.document_id} className="rounded border border-gray-200 p-2">
                <span className="mr-2">{review.title}</span>
                <span className="font-mono text-xs text-gray-500">{`${review.overdue_days} ${t.data.overdueDays}`}</span>
              </li>
            ))}
          </ul>
        )
      ) : null}
      <WhyItMattersPanel stage="data" />
    </section>
  );
}
