"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/context";
import type { Locale } from "@/i18n";
import { api } from "@/lib/api-client";

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
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authStatus, setAuthStatus] = useState("");

  // Restore the signed-in state when a valid session cookie already exists (page reload / new route).
  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((me) => {
        if (!cancelled) setAuthStatus(`Signed in as ${me.email}`);
      })
      .catch(() => {
        /* not signed in: leave the login form as is */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const lifecycleLabel = locale === "id" ? "Navigasi siklus hidup" : "Lifecycle navigation";
  const featuresLabel = t.nav.features;

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-blue-700 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        {t.app.skipToContent}
      </a>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold">{t.app.title}</span>
          <span className="hidden text-sm text-gray-500 sm:inline">
            {t.app.subtitle}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={async (event) => {
              event.preventDefault();
              setAuthStatus("Signing in...");
              try {
                await api.login({ email, password });
                setPassword("");
                setAuthStatus(`Signed in as ${email}`);
              } catch (error) {
                setAuthStatus(error instanceof Error ? error.message : "Sign in failed");
              }
            }}
          >
            <label className="sr-only" htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Email"
              className="w-40 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <label className="sr-only" htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              className="w-40 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700"
            >
              Sign in
            </button>
            {authStatus ? <span className="text-xs text-gray-600">{authStatus}</span> : null}
          </form>
          <button
            type="button"
            onClick={() => setLocale((locale === "en" ? "id" : "en") as Locale)}
            className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
          >
            {t.lang.switch}
          </button>
        </div>
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
          <nav aria-label={featuresLabel}>
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

        <main id="main-content" tabIndex={-1} className="flex-1 p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
