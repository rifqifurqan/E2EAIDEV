"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { getDictionary, dictionaries, type Dictionary, type Locale } from "./index";

interface I18nContextValue {
  locale: Locale;
  t: Dictionary;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

const STORAGE_KEY = "e2eai.locale";

function readStoredLocale(): Locale | null {
  try {
    const value = globalThis.localStorage?.getItem(STORAGE_KEY);
    return value && value in dictionaries ? (value as Locale) : null;
  } catch {
    return null; // storage blocked (private mode / policy): fall back to the default
  }
}

function storeLocale(locale: Locale): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, locale);
  } catch {
    /* storage blocked: the choice just won't survive a reload */
  }
}

export function I18nProvider({
  children,
  defaultLocale = "en",
}: {
  children: ReactNode;
  defaultLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(defaultLocale);
  const t = getDictionary(locale);

  // UAT-I18N-002: the language choice used to reset to English on every full page load (the nav
  // uses plain links). Restore it after mount so server and client markup still match on hydration.
  useEffect(() => {
    const stored = readStoredLocale();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time post-hydration restore
    if (stored) setLocaleState(stored);
  }, []);

  // Screen readers pick the voice from <html lang>; keep it in step with the visible language.
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    storeLocale(newLocale);
  }, []);

  return (
    <I18nContext.Provider value={{ locale, t, setLocale }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return ctx;
}
