"use client";

import { useI18n } from "@/i18n/context";
import type { Locale } from "@/i18n";

const LIFECYCLE_STAGES = [
  "plan",
  "data",
  "build",
  "test",
  "release",
  "operate",
  "improve",
] as const;

const FEATURE_LINKS = ["documents", "chat", "admin"] as const;

const STAGE_PATHS: Record<(typeof LIFECYCLE_STAGES)[number], string> = {
  plan: "/plan",
  data: "/data",
  build: "/build",
  test: "/test",
  release: "/release",
  operate: "/operate",
  improve: "/improve",
};

const FEATURE_PATHS: Record<(typeof FEATURE_LINKS)[number], string> = {
  documents: "/documents",
  chat: "/chat",
  admin: "/admin",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { locale, t, setLocale } = useI18n();

  const lifecycleLabel = locale === "id" ? "Navigasi siklus hidup" : "Lifecycle navigation";

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold">{t.app.title}</span>
          <span className="hidden text-sm text-gray-500 sm:inline">
            {t.app.subtitle}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setLocale(locale === "en" ? "id" : "en" as Locale)}
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
        >
          {t.lang.switch}
        </button>
      </header>

      <nav aria-label={lifecycleLabel} className="border-b border-gray-100 bg-gray-50 px-4">
        <ul className="flex flex-wrap gap-1 py-2">
          {LIFECYCLE_STAGES.map((stage) => (
            <li key={stage}>
              <a
                href={STAGE_PATHS[stage]}
                className="inline-block rounded px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-white hover:text-blue-700"
              >
                {t.nav[stage]}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex flex-1">
        <aside className="hidden w-48 border-r border-gray-100 bg-white p-4 md:block">
          <nav aria-label="Features">
            <ul className="space-y-1">
              {FEATURE_LINKS.map((feat) => (
                <li key={feat}>
                  <a
                    href={FEATURE_PATHS[feat]}
                    className="block rounded px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-blue-700"
                  >
                    {t.nav[feat]}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
