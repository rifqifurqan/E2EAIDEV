"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type ModelVersion } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { useLoadMore } from "@/lib/use-load-more";
import { LoadMore } from "./load-more";
import { WhyItMattersPanel } from "./why-it-matters-panel";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function ModelRow({ model, onDone }: { model: ModelVersion; onDone: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const hasScores = Object.keys(model.eval_scores).length > 0;
  const [runId, setRunId] = useState("");
  const [attachFailed, setAttachFailed] = useState(false);
  const runIdValid = UUID_RE.test(runId.trim());

  async function attach() {
    setAttachFailed(false);
    setBusy(true);
    try {
      await api.attachEvalRun(model.name, model.version, runId.trim());
      setRunId("");
    } catch {
      setAttachFailed(true);
    } finally {
      setBusy(false);
      onDone();
    }
  }

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
      {model.approval_status === "pending" ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <label htmlFor={`run-${model.name}-${model.version}`}>
            <span className="mr-1">{t.build.evalRunId}</span>
            <input
              id={`run-${model.name}-${model.version}`}
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
              className="rounded border border-gray-300 px-2 py-0.5 font-mono text-xs"
            />
          </label>
          <button
            type="button"
            disabled={busy || !runIdValid}
            onClick={attach}
            className="rounded border border-blue-400 px-2 py-0.5 text-xs text-blue-700 disabled:opacity-50"
          >
            {t.build.attachRun}
          </button>
        </div>
      ) : null}
      {failed ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {t.build.decisionFailed}
        </p>
      ) : null}
      {attachFailed ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {t.build.attachFailed}
        </p>
      ) : null}
    </li>
  );
}

export function BuildScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const state = useAdminData(() => api.listModels(), reloadKey);
  const more = useLoadMore(
    state.kind === "ready" ? state.data.models : undefined,
    state.kind === "ready" ? state.data.next_cursor : null,
    async (cursor: string) => {
      const page = await api.listModelsPage(cursor);
      return { items: page.models, next_cursor: page.next_cursor };
    },
  );
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [parent, setParent] = useState("");
  const [regBusy, setRegBusy] = useState(false);
  const [regFailed, setRegFailed] = useState(false);

  async function register(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRegFailed(false);
    setRegBusy(true);
    try {
      await api.registerModel(name.trim(), version.trim(), parent.trim() === "" ? undefined : parent.trim());
      setName("");
      setVersion("");
      setParent("");
    } catch {
      setRegFailed(true);
    } finally {
      setRegBusy(false);
      setReloadKey((key) => key + 1);
    }
  }

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
        <form onSubmit={register} className="mb-4 flex flex-wrap items-end gap-3 rounded border border-gray-200 p-3 text-sm">
          <label htmlFor="model-name">
            <span className="mr-1">{t.build.modelName}</span>
            <input
              id="model-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            />
          </label>
          <label htmlFor="model-version">
            <span className="mr-1">{t.build.version}</span>
            <input
              id="model-version"
              value={version}
              onChange={(event) => setVersion(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            />
          </label>
          <label htmlFor="model-parent">
            <span className="mr-1">{t.build.parentVersion}</span>
            <input
              id="model-parent"
              value={parent}
              onChange={(event) => setParent(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={regBusy || name.trim() === "" || version.trim() === ""}
            className="rounded border border-blue-400 px-3 py-1 text-sm text-blue-700 disabled:opacity-50"
          >
            {t.build.register}
          </button>
          {regFailed ? (
            <p role="alert" className="w-full text-sm text-red-700">
              {t.build.registerFailed}
            </p>
          ) : null}
        </form>
      ) : null}
      {state.kind === "ready" ? (
        more.items.length === 0 ? (
          <p className="text-sm text-gray-500">{t.build.noItems}</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {more.items.map((model) => (
              <ModelRow
                key={`${model.name}@${model.version}`}
                model={model}
                onDone={() => setReloadKey((key) => key + 1)}
              />
            ))}
          </ul>
        )
      ) : null}
        {state.kind === "ready" ? (
          <LoadMore hasMore={more.hasMore} busy={more.busy} failed={more.failed} onLoadMore={more.loadMore} />
        ) : null}
      <WhyItMattersPanel stage="build" />
    </section>
  );
}
