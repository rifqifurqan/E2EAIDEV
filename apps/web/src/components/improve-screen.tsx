"use client";

import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { WhyItMattersPanel } from "./why-it-matters-panel";

export function ImproveScreen() {
  const { t } = useI18n();
  const state = useAdminData(() => api.listFlywheel());

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.improve.title}</h1>
      {state.kind === "loading" ? <p>{t.improve.loading}</p> : null}
      {state.kind === "forbidden" ? (
        <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
          {t.improve.adminOnly}
        </p>
      ) : null}
      {state.kind === "error" ? (
        <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
          {t.improve.loadFailed}
        </p>
      ) : null}
      {state.kind === "ready" ? (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-lg font-semibold">{t.improve.byStatus}</h2>
          <ul className="mb-4 flex flex-wrap gap-3 text-sm">
            {Object.entries(state.data.by_status).map(([status, count]) => (
              <li key={status} className="rounded bg-gray-100 px-2 py-1">{`${status}: ${count}`}</li>
            ))}
          </ul>
          <h2 className="mb-2 text-lg font-semibold">{t.improve.queue}</h2>
          {state.data.items.length === 0 ? (
            <p className="text-sm text-gray-500">{t.improve.noItems}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {state.data.items.map((item) => (
                <li key={item.id} className="rounded border border-gray-200 p-2">
                  <span className="mr-2 font-mono text-xs text-gray-500">{item.status}</span>
                  <span>{item.question}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
      <WhyItMattersPanel stage="improve" />
    </section>
  );
}
