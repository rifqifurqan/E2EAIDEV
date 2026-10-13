"use client";

import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";

export function EvalScreen() {
  const { t } = useI18n();
  const runs = useAdminData(() => api.listEvalRuns());

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.eval.title}</h1>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t.eval.newDataset}
        </button>
        <button
          type="button"
          className="rounded border border-blue-300 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
        >
          {t.eval.runEval}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Datasets */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.eval.datasets}</h2>
          <p className="text-sm text-gray-500">{t.eval.noDatasets}</p>
        </div>

        {/* Runs */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.eval.runs}</h2>
          {runs.kind === "loading" ? <p>{t.eval.runsLoading}</p> : null}
          {runs.kind === "forbidden" ? (
            <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
              {t.eval.runsAdminOnly}
            </p>
          ) : null}
          {runs.kind === "error" ? (
            <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
              {t.eval.runsLoadFailed}
            </p>
          ) : null}
          {runs.kind === "ready" ? (
            runs.data.runs.length === 0 ? (
              <p className="text-sm text-gray-500">{t.eval.noRuns}</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {runs.data.runs.map((run) => (
                  <li key={run.id} className="rounded border border-gray-200 p-2">
                    <span className="mr-2">{run.adapter}</span>
                    <span className="mr-2 font-mono text-xs">{run.status}</span>
                    <span className="block text-xs text-gray-500">
                      {Object.entries(run.metrics)
                        .map(([name, value]) => `${name}: ${String(value)}`)
                        .join(", ")}
                    </span>
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      </div>

      {/* Permission Leak Summary */}
      <div className="mt-6 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
        <h2 className="mb-2 text-lg font-semibold text-yellow-800">
          {t.eval.leakSummary}
        </h2>
        <p className="text-sm text-green-700">{t.eval.noLeaks}</p>
      </div>
    </section>
  );
}
