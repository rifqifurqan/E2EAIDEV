"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type OrgSnapshot } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";

const RUNBOOK_BASE = "/docs/runbooks";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const RUNBOOK_FILES: { key: keyof typeof import("@/i18n/en").default.admin.runbookLinks; file: string }[] = [
  { key: "serviceDown", file: "service-down" },
  { key: "restoreBackup", file: "restore-from-backup" },
  { key: "modelFailing", file: "model-endpoint-failing" },
  { key: "vectorDegraded", file: "vector-store-degraded" },
  { key: "permissionLag", file: "permission-sync-lag" },
  { key: "diskFull", file: "disk-full" },
  { key: "leakedKey", file: "leaked-key" },
];

export function AdminScreen() {
  const { t } = useI18n();
  const [showDeactivate, setShowDeactivate] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const org = useAdminData<OrgSnapshot>(() => api.getOrgSnapshot());

  const target = targetId.trim();
  const owner = ownerId.trim();
  // Both must be UUIDs and different: assets cannot be transferred to the user being deactivated.
  const valid = UUID_RE.test(target) && UUID_RE.test(owner) && target.toLowerCase() !== owner.toLowerCase();

  async function deactivate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || busy) return;
    setFailed(false);
    setSummary(null);
    setBusy(true);
    try {
      const result = await api.deactivateUser(target, { transfer_to_id: owner });
      setTargetId("");
      setOwnerId("");
      setSummary(
        `${t.admin.userDeactivated}: ${result.documents_transferred} ${t.admin.documentsWord}, ` +
          `${result.folders_transferred} ${t.admin.foldersWord}, ${result.sessions_purged} ${t.admin.sessionsWord}`,
      );
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.admin.title}</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Configuration-as-code export */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.configExport}</h2>
          <p className="mb-3 text-sm text-gray-600">
            {t.admin.configExportDescription}
          </p>
          <a
            href="/api/v1/admin/config/export?format=yaml"
            download="e2eai.yaml"
            className="inline-flex rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            {t.admin.exportConfiguration}
          </a>
        </div>

        {/* Offboarding */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.offboarding}</h2>
          <p className="mb-3 text-sm text-gray-600">
            {t.admin.transferTo}
          </p>
          <button
            type="button"
            onClick={() => setShowDeactivate((open) => !open)}
            className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            {t.admin.deactivateUser}
          </button>
          {showDeactivate ? (
            <form onSubmit={deactivate} className="mt-3 flex flex-col gap-2 text-sm">
              <label htmlFor="deactivate-target">
                <span className="mr-1">{t.admin.deactivateTarget}</span>
                <input
                  id="deactivate-target"
                  value={targetId}
                  onChange={(event) => setTargetId(event.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                />
              </label>
              <label htmlFor="deactivate-owner">
                <span className="mr-1">{t.admin.newOwner}</span>
                <input
                  id="deactivate-owner"
                  value={ownerId}
                  onChange={(event) => setOwnerId(event.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                />
              </label>
              <button
                type="submit"
                disabled={busy || !valid}
                className="self-start rounded border border-red-500 px-3 py-1 text-sm text-red-700 disabled:opacity-50"
              >
                {t.admin.confirmDeactivation}
              </button>
              {summary !== null ? (
                <p role="status" className="text-sm text-green-700">
                  {summary}
                </p>
              ) : null}
              {failed ? (
                <p role="alert" className="text-sm text-red-700">
                  {t.admin.deactivateFailed}
                </p>
              ) : null}
            </form>
          ) : null}
        </div>

        {/* Organization */}
        <section aria-labelledby="admin-org-title" className="rounded-lg border border-gray-200 p-4 lg:col-span-2">
          <h2 id="admin-org-title" className="mb-3 text-lg font-semibold">
            {t.admin.organization}
          </h2>
          {org.kind === "loading" ? <p className="text-sm text-gray-600">{t.admin.orgLoading}</p> : null}
          {org.kind === "forbidden" ? (
            <p role="alert" className="text-sm text-amber-700">
              {t.admin.orgAdminOnly}
            </p>
          ) : null}
          {org.kind === "error" ? (
            <p role="alert" className="text-sm text-red-700">
              {t.admin.orgLoadFailed}
            </p>
          ) : null}
          {org.kind === "ready" ? (
            <div className="grid gap-4 md:grid-cols-3 text-sm">
              <div>
                <h3 className="mb-1 font-medium">{t.admin.divisions}</h3>
                {org.data.divisions.length === 0 ? (
                  <p className="text-gray-600">{t.admin.orgEmpty}</p>
                ) : (
                  <ul className="space-y-1">
                    {org.data.divisions.map((d) => (
                      <li key={d.id}>{d.name}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h3 className="mb-1 font-medium">{t.admin.teams}</h3>
                {org.data.teams.length === 0 ? (
                  <p className="text-gray-600">{t.admin.orgEmpty}</p>
                ) : (
                  <ul className="space-y-1">
                    {org.data.teams.map((team) => (
                      <li key={team.id}>{team.name}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h3 className="mb-1 font-medium">{t.admin.users}</h3>
                {org.data.users.length === 0 ? (
                  <p className="text-gray-600">{t.admin.orgEmpty}</p>
                ) : (
                  <ul className="space-y-1">
                    {org.data.users.map((u) => (
                      <li key={u.id}>
                        {u.display_name} <span className="text-gray-600">({u.email})</span>
                        {u.status === "disabled" ? <span className="ml-1 text-red-700">[{t.admin.statusDisabled}]</span> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : null}
        </section>

        {/* Runbooks */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.runbooks}</h2>
          <ul className="space-y-2">
            {RUNBOOK_FILES.map(({ key, file }) => (
              <li key={key}>
                <a
                  href={`${RUNBOOK_BASE}/${file}`}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {t.admin.runbookLinks[key]}
                </a>
              </li>
            ))}
          </ul>
        </div>

      </div>
    </section>
  );
}
