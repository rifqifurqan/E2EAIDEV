"use client";

import { useI18n } from "@/i18n/context";

export function BotReleaseScreen() {
  const { t } = useI18n();

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.bots.title}</h1>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t.bots.newBot}
        </button>
        <button
          type="button"
          className="rounded border border-blue-300 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
        >
          {t.bots.release}
        </button>
        <button
          type="button"
          className="rounded border border-orange-300 px-4 py-2 text-sm font-medium text-orange-700 hover:bg-orange-50"
        >
          {t.bots.rollback}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Bundles */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.bundles}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>

        {/* Grants */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.grants}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>

        {/* Scope */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.scope}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>
      </div>
    </section>
  );
}
