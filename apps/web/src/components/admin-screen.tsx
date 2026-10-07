"use client";

import { useI18n } from "@/i18n/context";

const RUNBOOK_BASE = "/docs/runbooks";

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

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.admin.title}</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Offboarding */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.offboarding}</h2>
          <p className="mb-3 text-sm text-gray-600">
            {t.admin.transferTo}
          </p>
          <button
            type="button"
            className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            {t.admin.deactivateUser}
          </button>
        </div>

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
