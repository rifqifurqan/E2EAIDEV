"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type ModelVersion } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { WhyItMattersPanel } from "./why-it-matters-panel";

function ModelRow({ model, onDone }: { model: ModelVersion; onDone: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const hasScores = Object.keys(model.eval_scores).length > 0;

  async function decide(decision: "approved" | "rejected") {
    setFailed(false);
    setBusy(true);
    try {
      await api.decideModel(model.name, model.version, decision);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      onDone();
    }
  }

  return (
    <li className="rounded border border-gray-200 p-2">
      <span className="mr-2 font-medium">{model.name}</span>
      <span className="mr-2 font-mono text-xs">{model.version}</span>
      <span className="font-mono text-xs text-gray-500">{model.approval_status}</span>
      {model.approval_status === "pending" ? (
        <span className="ml-3 inline-flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy || !hasScores}
            onClick={() => decide("approved")}
            className="rounded border border-green-400 px-2 py-0.5 text-xs text-green-700 disabled:opacity-50"
          >
            {t.build.approve}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide("rejected")}
            className="rounded border border-red-400 px-2 py-0.5 text-xs text-red-700 disabled:opacity-50"
          >
            {t.build.reject}
          </button>
          {!hasScores ? <span className="text-xs text-gray-500">{t.build.needsScore}</span> : null}
        </span>
      ) : null}
      {failed ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {t.build.decisionFailed}
        </p>
      ) : null}
    </li>
  );
}

export function BuildScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const state = useAdminData(() => api.listModels(), reloadKey);

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
              <ModelRow
                key={`${model.name}@${model.version}`}
                model={model}
                onDone={() => setReloadKey((key) => key + 1)}
              />
            ))}
          </ul>
        )
      ) : null}
      <WhyItMattersPanel stage="build" />
    </section>
  );
}
