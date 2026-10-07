"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";

type DocView = "my" | "shared" | "team";

export function DocumentsScreen() {
  const { t } = useI18n();
  const [activeView, setActiveView] = useState<DocView>("my");

  const tabs: { key: DocView; label: string }[] = [
    { key: "my", label: t.documents.myDocuments },
    { key: "shared", label: t.documents.sharedWithMe },
    { key: "team", label: t.documents.myTeam },
  ];

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.documents.title}</h1>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div role="tablist" className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={activeView === tab.key}
              onClick={() => setActiveView(tab.key)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${
                activeView === tab.key
                  ? "bg-blue-100 text-blue-800"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="search"
            role="searchbox"
            placeholder={t.documents.search}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t.documents.upload}
        </button>
        <button
          type="button"
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          {t.documents.share}
        </button>
        <button
          type="button"
          className="rounded border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
        >
          {t.documents.revoke}
        </button>
      </div>

      <div className="rounded-lg border border-gray-200 p-8 text-center text-gray-500">
        {t.documents.noDocuments}
      </div>
    </section>
  );
}
