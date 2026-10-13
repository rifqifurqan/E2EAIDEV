"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type AiIncident, type IncidentTransition, type ReportIncidentInput } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { useLoadMore } from "@/lib/use-load-more";
import { LoadMore } from "./load-more";
import { AdminScreen } from "./admin-screen";
import { WhyItMattersPanel } from "./why-it-matters-panel";

// Closing needs a post-incident record; the post-incident form is shown from "fixed" on.
const NEXT_STATUS: Record<string, IncidentTransition["to_status"] | undefined> = {
  reported: "triaged",
  triaged: "fixing",
  fixing: "fixed",
  fixed: "released",
  released: "closed",
};

function IncidentRow({ incident, onTransition }: { incident: AiIncident; onTransition: () => void }) {
  const { t } = useI18n();
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [summary, setSummary] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [pmBusy, setPmBusy] = useState(false);
  const [pmFailed, setPmFailed] = useState(false);
  const hasPostmortem = incident.postmortem != null;
  // "closed" is only reachable once a post-incident record exists (same rule as the API).
  const next = incident.status === "released" && !hasPostmortem ? undefined : NEXT_STATUS[incident.status];
  const showPostmortemForm = !hasPostmortem && ["fixed", "released"].includes(incident.status);
  const needsNotes = next === "fixed";
  const needsRef = next === "released";
  const needsText = needsNotes || needsRef;

  async function move() {
    if (next === undefined) return;
    const body: IncidentTransition = { to_status: next };
    if (needsNotes) body.fix_notes = extra.trim();
    if (needsRef) body.release_ref = extra.trim();
    setFailed(false);
    setBusy(true);
    try {
      await api.transitionIncident(incident.id, body);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      onTransition();
    }
  }

  async function savePostmortem() {
    setPmFailed(false);
    setPmBusy(true);
    try {
      await api.recordPostmortem(incident.id, { summary: summary.trim(), root_cause: rootCause.trim() });
    } catch {
      setPmFailed(true);
    } finally {
      setPmBusy(false);
      onTransition();
    }
  }

  return (
    <li className="rounded border border-gray-200 p-2">
      <span className="mr-2 font-mono text-xs uppercase">{incident.severity}</span>
      <span className="mr-2 font-mono text-xs text-gray-500">{incident.status}</span>
      <span>{incident.title}</span>
      {next !== undefined ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {needsText ? (
            <label className="text-xs">
              <span className="mr-1">{needsNotes ? t.operate.fixNotes : t.operate.releaseRef}</span>
              <input
                value={extra}
                onChange={(event) => setExtra(event.target.value)}
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
            </label>
          ) : null}
          <button
            type="button"
            disabled={busy || (needsText && extra.trim() === "")}
            onClick={move}
            className="rounded border border-blue-400 px-2 py-0.5 text-xs text-blue-700 disabled:opacity-50"
          >
            {`${t.operate.moveTo} ${next}`}
          </button>
        </div>
      ) : null}
      {failed ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {t.operate.transitionFailed}
        </p>
      ) : null}
      {showPostmortemForm ? (
        <div className="mt-2 flex flex-wrap items-end gap-2 text-xs">
          <label>
            <span className="mr-1">{t.operate.pmSummary}</span>
            <input
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-xs"
            />
          </label>
          <label>
            <span className="mr-1">{t.operate.pmRootCause}</span>
            <input
              value={rootCause}
              onChange={(event) => setRootCause(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-xs"
            />
          </label>
          <button
            type="button"
            disabled={pmBusy || summary.trim() === "" || rootCause.trim() === ""}
            onClick={savePostmortem}
            className="rounded border border-blue-400 px-2 py-0.5 text-xs text-blue-700 disabled:opacity-50"
          >
            {t.operate.pmRecord}
          </button>
        </div>
      ) : null}
      {pmFailed ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {t.operate.pmFailed}
        </p>
      ) : null}
    </li>
  );
}

const SEVERITIES = ["sev1", "sev2", "sev3", "sev4"] as const;

function ReportIncidentForm({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>("sev3");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailed(false);
    setBusy(true);
    try {
      const body: ReportIncidentInput = { title: title.trim(), severity };
      if (description.trim() !== "") body.description = description.trim();
      await api.reportIncident(body);
      setTitle("");
      setDescription("");
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      onDone();
    }
  }

  return (
    <form onSubmit={submit} className="mb-4 flex flex-wrap items-end gap-3 rounded border border-gray-200 p-3 text-sm">
      <label htmlFor="incident-title">
        <span className="mr-1">{t.operate.reportTitle}</span>
        <input
          id="incident-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </label>
      <label htmlFor="incident-severity">
        <span className="mr-1">{t.operate.reportSeverity}</span>
        <select
          id="incident-severity"
          value={severity}
          onChange={(event) => setSeverity(event.target.value as (typeof SEVERITIES)[number])}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          {SEVERITIES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor="incident-description">
        <span className="mr-1">{t.operate.reportDescription}</span>
        <input
          id="incident-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </label>
      <button
        type="submit"
        disabled={busy || title.trim() === ""}
        className="rounded border border-blue-400 px-3 py-1 text-sm text-blue-700 disabled:opacity-50"
      >
        {t.operate.reportSubmit}
      </button>
      {failed ? (
        <p role="alert" className="w-full text-sm text-red-700">
          {t.operate.reportFailed}
        </p>
      ) : null}
    </form>
  );
}

async function fetchIncidentsPage(cursor: string) {
  const page = await api.listIncidentsPage(cursor);
  return { items: page.incidents, next_cursor: page.next_cursor };
}

export function OperateScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const state = useAdminData(() => api.listIncidents(), reloadKey);
  const more = useLoadMore(
    state.kind === "ready" ? state.data.incidents : undefined,
    state.kind === "ready" ? state.data.next_cursor : null,
    fetchIncidentsPage,
  );

  return (
    <div className="space-y-6">
      <AdminScreen />
      <section aria-labelledby="ai-incidents-heading">
        <h2 id="ai-incidents-heading" className="mb-3 text-lg font-semibold">
          {t.operate.incidentsTitle}
        </h2>
        <ReportIncidentForm onDone={() => setReloadKey((key) => key + 1)} />
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
          more.items.length === 0 ? (
            <p className="text-sm text-gray-500">{t.operate.noIncidents}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {more.items.map((incident) => (
                <IncidentRow key={incident.id} incident={incident} onTransition={() => setReloadKey((key) => key + 1)} />
              ))}
            </ul>
          )
        ) : null}
        {state.kind === "ready" ? (
          <LoadMore hasMore={more.hasMore} busy={more.busy} failed={more.failed} onLoadMore={more.loadMore} />
        ) : null}
      </section>
      <WhyItMattersPanel stage="operate" />
    </div>
  );
}
