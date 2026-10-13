"use client";

import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { WhyItMattersPanel } from "./why-it-matters-panel";

export function BuildScreen() {
  const { t } = useI18n();
  const state = useAdminData(() => api.listModels());

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.nav.build}</h1>
      <h2 className="mb-3 text-lg font-semibold">{t.build.title}</h2>
      {state.kind === "loading" ? <p>{t.build.loading}</p> : null}
      {state.kind === "forbidden" ? (
        <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
          {t.build.signIn}
        </p>
      ) : null}
      {state.kind === "error" ? (
        <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
          {t.build.loadFailed}
        </p>
      ) : null}
      {state.kind === "ready" ? (
        state.data.models.length === 0 ? (
          <p className="text-sm text-gray-500">{t.build.noItems}</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {state.data.models.map((model) => (
              <li key={`${model.name}@${model.version}`} className="rounded border border-gray-200 p-2">
                <span className="mr-2 font-medium">{model.name}</span>
                <span className="mr-2 font-mono text-xs">{model.version}</span>
                <span className="font-mono text-xs text-gray-500">{model.approval_status}</span>
              </li>
            ))}
          </ul>
        )
      ) : null}
      <WhyItMattersPanel stage="build" />
    </section>
  );
}
