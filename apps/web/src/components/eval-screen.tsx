"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type EvalRunSummary } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { useLoadMore } from "@/lib/use-load-more";
import { LoadMore } from "./load-more";

const LEAK_ADAPTER = "permission-leak.local";

function LeakSummary({ runs }: { runs: EvalRunSummary[] }) {
  const { t } = useI18n();
  // The API lists runs newest first; the first permission-leak run is the latest.
  const latest = runs.find((run) => run.adapter === LEAK_ADAPTER);
  const leaks = latest === undefined ? Number.NaN : Number(latest.metrics.leaks);
  if (latest === undefined || !Number.isFinite(leaks)) {
    return <p className="text-sm text-gray-700">{t.eval.noLeakRun}</p>;
  }
  const probes = Number(latest.metrics.probes);
  return (
    <div data-testid="leak-summary-result">
      {leaks === 0 ? (
        <p className="text-sm text-green-700">{t.eval.noLeaks}</p>
      ) : (
        <p role="alert" className="text-sm font-semibold text-red-700">
          {`${t.eval.leakCount}: ${leaks}`}
        </p>
      )}
      {Number.isFinite(probes) ? (
        <p className="text-xs text-gray-600">{`${t.eval.leakProbes}: ${probes}`}</p>
      ) : null}
    </div>
  );
}

export function EvalScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const runs = useAdminData(() => api.listEvalRuns(), reloadKey);
  const datasets = useAdminData(() => api.listEvalDatasets(), reloadKey);
  const moreRuns = useLoadMore(
    runs.kind === "ready" ? runs.data.runs : undefined,
    runs.kind === "ready" ? runs.data.next_cursor : null,
    async (cursor: string) => {
      const page = await api.listEvalRunsPage(cursor);
      return { items: page.runs, next_cursor: page.next_cursor };
    },
  );
  const moreDatasets = useLoadMore(
    datasets.kind === "ready" ? datasets.data.datasets : undefined,
    datasets.kind === "ready" ? datasets.data.next_cursor : null,
    async (cursor: string) => {
      const page = await api.listEvalDatasetsPage(cursor);
      return { items: page.datasets, next_cursor: page.next_cursor };
    },
  );
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [itemsText, setItemsText] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [runError, setRunError] = useState(false);
  const [busy, setBusy] = useState(false);

  const [pickedId, setPickedId] = useState<string | null>(null);
  const datasetList = datasets.kind === "ready" ? datasets.data.datasets : [];
  // Default to the newest dataset (the API lists newest first) unless the user picked another one.
  const targetDataset = datasetList.find((dataset) => dataset.id === pickedId) ?? datasetList[0] ?? null;

  async function submitDataset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let items: unknown;
    try {
      items = JSON.parse(itemsText);
    } catch {
      items = null;
    }
    if (!Array.isArray(items) || items.length === 0) {
      setFormError(t.eval.itemsInvalid);
      return;
    }
    setFormError(null);
    setBusy(true);
    try {
      await api.createDataset(name.trim(), "manual", items);
      setName("");
      setItemsText("");
      setFormOpen(false);
      setReloadKey((key) => key + 1);
    } catch {
      setFormError(t.eval.createFailed);
    } finally {
      setBusy(false);
    }
  }

  async function runLatest() {
    if (targetDataset === null) return;
    setRunError(false);
    setBusy(true);
    try {
      await api.runEval(targetDataset.id, "ragas.local");
      setReloadKey((key) => key + 1);
    } catch {
      setRunError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.eval.title}</h1>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setFormOpen((open) => !open)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t.eval.newDataset}
        </button>
        <button
          type="button"
          onClick={runLatest}
          disabled={targetDataset === null || busy}
          className="rounded border border-blue-300 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
        >
          {t.eval.runEval}
        </button>
      </div>

      {runError ? (
        <p role="alert" className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm">
          {t.eval.runFailed}
        </p>
      ) : null}
      {targetDataset !== null ? (
        <label htmlFor="eval-target" className="mb-4 block text-sm">
          <span className="mr-2">{t.eval.runTarget}</span>
          <select
            id="eval-target"
            value={targetDataset.id}
            onChange={(event) => setPickedId(event.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {datasetList.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {`${dataset.name} (v${dataset.version})`}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {formOpen ? (
        <form onSubmit={submitDataset} className="mb-6 rounded-lg border border-gray-200 p-4">
          <label className="block text-sm font-medium" htmlFor="dataset-name">
            {t.eval.datasetName}
            <input
              id="dataset-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="mt-3 block text-sm font-medium" htmlFor="dataset-items">
            {t.eval.datasetItems}
            <textarea
              id="dataset-items"
              value={itemsText}
              onChange={(event) => setItemsText(event.target.value)}
              required
              rows={5}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 font-mono text-xs"
            />
          </label>
          {formError !== null ? (
            <p role="alert" className="mt-2 text-sm text-red-700">
              {formError}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={busy}
            className="mt-3 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {t.eval.createDataset}
          </button>
        </form>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Datasets */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.eval.datasets}</h2>
          {datasets.kind === "loading" ? <p>{t.eval.datasetsLoading}</p> : null}
          {datasets.kind === "forbidden" ? (
            <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
              {t.eval.datasetsAdminOnly}
            </p>
          ) : null}
          {datasets.kind === "error" ? (
            <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
              {t.eval.datasetsLoadFailed}
            </p>
          ) : null}
          {datasets.kind === "ready" ? (
            moreDatasets.items.length === 0 ? (
              <p className="text-sm text-gray-500">{t.eval.noDatasets}</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {moreDatasets.items.map((dataset) => (
                  <li key={dataset.id} className="rounded border border-gray-200 p-2">
                    <span className="mr-2">{dataset.name}</span>
                    <span className="text-xs text-gray-500">{`v${dataset.version} · ${dataset.source} · ${dataset.item_count}`}</span>
                  </li>
                ))}
              </ul>
            )
          ) : null}
          {datasets.kind === "ready" ? (
            <LoadMore
              hasMore={moreDatasets.hasMore}
              busy={moreDatasets.busy}
              failed={moreDatasets.failed}
              onLoadMore={moreDatasets.loadMore}
            />
          ) : null}
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
            moreRuns.items.length === 0 ? (
              <p className="text-sm text-gray-500">{t.eval.noRuns}</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {moreRuns.items.map((run) => (
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
          {runs.kind === "ready" ? (
            <LoadMore hasMore={moreRuns.hasMore} busy={moreRuns.busy} failed={moreRuns.failed} onLoadMore={moreRuns.loadMore} />
          ) : null}
        </div>
      </div>

      {/* Permission Leak Summary (derived from the newest permission-leak run) */}
      <div className="mt-6 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
        <h2 className="mb-2 text-lg font-semibold text-yellow-800">
          {t.eval.leakSummary}
        </h2>
        {runs.kind === "loading" ? <p className="text-sm">{t.eval.runsLoading}</p> : null}
        {runs.kind === "forbidden" ? (
          <p className="text-sm">{t.eval.runsAdminOnly}</p>
        ) : null}
        {runs.kind === "error" ? <p className="text-sm">{t.eval.runsLoadFailed}</p> : null}
        {runs.kind === "ready" ? <LeakSummary runs={runs.data.runs} /> : null}
      </div>
    </section>
  );
}
