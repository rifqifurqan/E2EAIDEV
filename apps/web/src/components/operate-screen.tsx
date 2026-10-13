"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type AiIncident, type IncidentTransition } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { AdminScreen } from "./admin-screen";
import { WhyItMattersPanel } from "./why-it-matters-panel";

// Closing needs a post-incident record (no UI yet), so the buttons stop at "released".
const NEXT_STATUS: Record<string, IncidentTransition["to_status"] | undefined> = {
  reported: "triaged",
  triaged: "fixing",
  fixing: "fixed",
  fixed: "released",
};

function IncidentRow({ incident, onTransition }: { incident: AiIncident; onTransition: () => void }) {
  const { t } = useI18n();
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const next = NEXT_STATUS[incident.status];
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
    </li>
  );
}

export function OperateScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const state = useAdminData(() => api.listIncidents(), reloadKey);

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
                <IncidentRow key={incident.id} incident={incident} onTransition={() => setReloadKey((key) => key + 1)} />
              ))}
            </ul>
          )
        ) : null}
      </section>
      <WhyItMattersPanel stage="operate" />
    </div>
  );
}
