"use client";

import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { AdminScreen } from "./admin-screen";
import { WhyItMattersPanel } from "./why-it-matters-panel";

export function OperateScreen() {
  const { t } = useI18n();
  const state = useAdminData(() => api.listIncidents());

  return (
    <div className="space-y-6">
      <AdminScreen />
      <section aria-labelledby="ai-incidents-heading">
        <h2 id="ai-incidents-heading" className="mb-3 text-lg font-semibold">
          {t.operate.incidentsTitle}
        </h2>
        {state.kind === "loading" ? <p>{t.operate.loading}</p> : null}
        {state.kind === "forbidden" ? (
          <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
            {t.operate.adminOnly}
          </p>
        ) : null}
        {state.kind === "error" ? (
          <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
            {t.operate.loadFailed}
          </p>
        ) : null}
        {state.kind === "ready" ? (
          state.data.incidents.length === 0 ? (
            <p className="text-sm text-gray-500">{t.operate.noIncidents}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {state.data.incidents.map((incident) => (
                <li key={incident.id} className="rounded border border-gray-200 p-2">
                  <span className="mr-2 font-mono text-xs uppercase">{incident.severity}</span>
                  <span className="mr-2 font-mono text-xs text-gray-500">{incident.status}</span>
                  <span>{incident.title}</span>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>
      <WhyItMattersPanel stage="operate" />
    </div>
  );
}
