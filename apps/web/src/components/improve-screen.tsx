"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { useLoadMore } from "@/lib/use-load-more";
import { LoadMore } from "./load-more";
import { WhyItMattersPanel } from "./why-it-matters-panel";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function LinkControls({
  item,
  busy,
  onLink,
}: {
  item: { id: string; status: string };
  busy: boolean;
  onLink: (action: () => Promise<unknown>) => void;
}) {
  const { t } = useI18n();
  const [value, setValue] = useState("");
  const isReeval = item.status === "exported";
  const trimmed = value.trim();
  const valid = isReeval ? UUID_RE.test(trimmed) : trimmed !== "";
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
      <label htmlFor={`link-${item.id}`}>
        <span className="mr-1">{isReeval ? t.improve.evalRunId : t.improve.releaseRef}</span>
        <input
          id={`link-${item.id}`}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="rounded border border-gray-300 px-2 py-0.5 font-mono text-xs"
        />
      </label>
      <button
        type="button"
        disabled={busy || !valid}
        onClick={() =>
          onLink(() => (isReeval ? api.linkFlywheelReeval(item.id, trimmed) : api.linkFlywheelRelease(item.id, trimmed)))
        }
        className="rounded border border-blue-400 px-2 py-0.5 text-xs text-blue-700 disabled:opacity-50"
      >
        {isReeval ? t.improve.linkReeval : t.improve.linkRelease}
      </button>
    </div>
  );
}

export function ImproveScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const state = useAdminData(() => api.listFlywheel(), reloadKey);
  const more = useLoadMore(
    state.kind === "ready" ? state.data.items : undefined,
    state.kind === "ready" ? state.data.next_cursor : null,
    api.listFlywheelPage,
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [triageFailed, setTriageFailed] = useState(false);
  const [exportName, setExportName] = useState("");
  const [exportTarget, setExportTarget] = useState<"eval" | "finetune">("eval");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportFailed, setExportFailed] = useState(false);
  const [exportResult, setExportResult] = useState<string | null>(null);

  async function exportAccepted() {
    setExportFailed(false);
    setExportResult(null);
    setExportBusy(true);
    try {
      const result = await api.exportFlywheel(exportTarget, exportName.trim());
      setExportResult(`${t.improve.exported} ${result.items} ${t.improve.exportedTo} ${result.name} (v${result.version})`);
      setExportName("");
    } catch {
      setExportFailed(true);
    } finally {
      setExportBusy(false);
      setReloadKey((key) => key + 1);
    }
  }

  const [linkFailed, setLinkFailed] = useState(false);

  async function link(id: string, action: () => Promise<unknown>) {
    setLinkFailed(false);
    setBusyId(id);
    try {
      await action();
    } catch {
      setLinkFailed(true);
    } finally {
      setBusyId(null);
      setReloadKey((key) => key + 1);
    }
  }

  async function triage(id: string, decision: "accept" | "dismiss", target?: "eval" | "finetune") {
    setTriageFailed(false);
    setBusyId(id);
    try {
      await api.triageFlywheelItem(id, decision, target);
    } catch {
      setTriageFailed(true);
    } finally {
      setBusyId(null);
      setReloadKey((key) => key + 1);
    }
  }

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
          {(state.data.by_status.accepted ?? 0) > 0 ? (
            <div className="mb-4 rounded border border-gray-200 p-3">
              <h2 className="mb-2 text-lg font-semibold">{t.improve.exportTitle}</h2>
              <div className="flex flex-wrap items-end gap-3 text-sm">
                <label htmlFor="export-name">
                  <span className="mr-1">{t.improve.datasetName}</span>
                  <input
                    id="export-name"
                    value={exportName}
                    onChange={(event) => setExportName(event.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                </label>
                <label htmlFor="export-target">
                  <span className="mr-1">{t.improve.exportTarget}</span>
                  <select
                    id="export-target"
                    value={exportTarget}
                    onChange={(event) => setExportTarget(event.target.value as "eval" | "finetune")}
                    className="rounded border border-gray-300 px-2 py-1 text-sm"
                  >
                    <option value="eval">{t.improve.targetEval}</option>
                    <option value="finetune">{t.improve.targetFinetune}</option>
                  </select>
                </label>
                <button
                  type="button"
                  disabled={exportBusy || exportName.trim() === ""}
                  onClick={exportAccepted}
                  className="rounded border border-blue-400 px-3 py-1 text-sm text-blue-700 disabled:opacity-50"
                >
                  {t.improve.exportAccepted}
                </button>
              </div>
              {exportResult !== null ? <p className="mt-2 text-sm text-green-700">{exportResult}</p> : null}
              {exportFailed ? (
                <p role="alert" className="mt-2 text-sm text-red-700">
                  {t.improve.exportFailed}
                </p>
              ) : null}
            </div>
          ) : null}
          <h2 className="mb-2 text-lg font-semibold">{t.improve.queue}</h2>
          {triageFailed ? (
            <p role="alert" className="mb-2 rounded border border-red-300 bg-red-50 p-3 text-sm">
              {t.improve.triageFailed}
            </p>
          ) : null}
          {linkFailed ? (
            <p role="alert" className="mb-2 rounded border border-red-300 bg-red-50 p-3 text-sm">
              {t.improve.linkFailed}
            </p>
          ) : null}
          {more.items.length === 0 ? (
            <p className="text-sm text-gray-500">{t.improve.noItems}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {more.items.map((item) => (
                <li key={item.id} className="rounded border border-gray-200 p-2">
                  <span className="mr-2 font-mono text-xs text-gray-500">{item.status}</span>
                  <span>{item.question}</span>
                  {item.status === "queued" ? (
                    <span className="ml-3 inline-flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={busyId === item.id || !item.correction}
                        onClick={() => triage(item.id, "accept", "eval")}
                        className="rounded border border-green-400 px-2 py-0.5 text-xs text-green-700 disabled:opacity-50"
                      >
                        {t.improve.acceptEval}
                      </button>
                      <button
                        type="button"
                        disabled={busyId === item.id || !item.correction}
                        onClick={() => triage(item.id, "accept", "finetune")}
                        className="rounded border border-green-400 px-2 py-0.5 text-xs text-green-700 disabled:opacity-50"
                      >
                        {t.improve.acceptFinetune}
                      </button>
                      <button
                        type="button"
                        disabled={busyId === item.id}
                        onClick={() => triage(item.id, "dismiss")}
                        className="rounded border border-gray-400 px-2 py-0.5 text-xs text-gray-700 disabled:opacity-50"
                      >
                        {t.improve.dismiss}
                      </button>
                    </span>
                  ) : null}
                  {item.status === "exported" || item.status === "reevaluated" ? (
                    <LinkControls item={item} busy={busyId === item.id} onLink={(action) => link(item.id, action)} />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <LoadMore hasMore={more.hasMore} busy={more.busy} failed={more.failed} onLoadMore={more.loadMore} />
        </div>
      ) : null}
      <WhyItMattersPanel stage="improve" />
    </section>
  );
}
