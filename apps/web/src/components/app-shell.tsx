"use client";

import { Fragment, useEffect, useState } from "react";
import { useI18n } from "@/i18n/context";
import type { Locale } from "@/i18n";
import { SESSION_EXPIRED_EVENT, api } from "@/lib/api-client";

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
  const [session, setSession] = useState<{ email: string; csrf: string } | null>(null);
  // Bumped on every sign-in so page content remounts and reloads with the new session (no stale "please sign in").
  const [contentKey, setContentKey] = useState(0);

  // Restore the signed-in state when a valid session cookie already exists (page reload / new route).
  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((me) => {
        if (!cancelled) setSession({ email: me.email, csrf: me.csrf_token ?? "" });
      })
      .catch(() => {
        /* not signed in: leave the login form as is */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // A data call got 401 mid-use: show the login form with a reason instead of a "Signed in" header over a broken page.
  useEffect(() => {
    const onExpired = () => {
      setSession(null);
      setAuthStatus(t.auth.sessionExpired);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [t.auth.sessionExpired]);

  const lifecycleLabel = locale === "id" ? "Navigasi siklus hidup" : "Lifecycle navigation";
  const featuresLabel = t.nav.features;
  const mobileFeaturesLabel = locale === "id" ? "Navigasi fitur seluler" : "Mobile feature navigation";

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
          {session ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-gray-600">{`${t.auth.signedInAs} ${session.email}`}</span>
              <button
                type="button"
                onClick={async () => {
                  try {
                    await api.logout(session.csrf);
                    setSession(null);
                    setAuthStatus("");
                  } catch {
                    setAuthStatus(t.auth.signOutFailed);
                  }
                }}
                className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
              >
                {t.auth.signOut}
              </button>
              {authStatus ? <span className="text-xs text-red-700">{authStatus}</span> : null}
            </div>
          ) : (
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={async (event) => {
              event.preventDefault();
              setAuthStatus(t.auth.signingIn);
              try {
                const res = await api.login({ email, password });
                setPassword("");
                setAuthStatus("");
                setSession({ email, csrf: res?.csrf_token ?? "" });
                setContentKey((key) => key + 1);
              } catch (error) {
                setAuthStatus(error instanceof Error ? error.message : t.auth.signInFailed);
              }
            }}
          >
            <label className="sr-only" htmlFor="login-email">{t.auth.email}</label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t.auth.email}
              className="w-40 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <label className="sr-only" htmlFor="login-password">{t.auth.password}</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t.auth.password}
              className="w-40 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700"
            >
              {t.auth.signIn}
            </button>
            {authStatus ? <span className="text-xs text-gray-600">{authStatus}</span> : null}
          </form>
          )}
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

      <nav aria-label={mobileFeaturesLabel} className="border-b border-gray-100 bg-white px-4 md:hidden">
        <ul className="flex flex-wrap gap-1 py-2">
          {FEATURE_LINKS.map((feat) => (
            <li key={feat}>
              <a
                href={FEATURE_PATHS[feat]}
                className="inline-block rounded px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:text-blue-700"
              >
                {t.nav[feat]}
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
          <Fragment key={contentKey}>{children}</Fragment>
        </main>
      </div>
    </div>
  );
}
