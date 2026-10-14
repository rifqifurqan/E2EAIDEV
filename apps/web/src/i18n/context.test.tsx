import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nProvider, useI18n } from "./context";

function Probe() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="docs">{t.nav.documents}</span>
      <button onClick={() => setLocale(locale === "en" ? "id" : "en")}>toggle</button>
    </div>
  );
}

/** In-memory Storage: this runtime's jsdom/Node pair does not always provide a working localStorage. */
function fakeStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => (data.has(k) ? data.get(k)! : null),
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  };
}

describe("I18nProvider locale persistence (UAT-I18N-002)", () => {
  beforeEach(() => vi.stubGlobal("localStorage", fakeStorage()));
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.lang = "en";
  });

  it("remembers the chosen language across a full page load", async () => {
    const first = render(<I18nProvider><Probe /></I18nProvider>);
    await userEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByTestId("locale")).toHaveTextContent("id");
    first.unmount(); // a full navigation throws React state away

    render(<I18nProvider><Probe /></I18nProvider>);
    expect(await screen.findByText("Dokumen")).toBeInTheDocument();
    expect(screen.getByTestId("locale")).toHaveTextContent("id");
  });

  it("ignores a corrupt stored value and keeps the default", () => {
    localStorage.setItem("e2eai.locale", "klingon");
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByTestId("locale")).toHaveTextContent("en");
  });

  it("keeps the document language attribute in sync for screen readers", async () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    await userEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(document.documentElement.lang).toBe("id");
  });

  it("still works when storage is unavailable (private mode)", async () => {
    vi.stubGlobal("localStorage", undefined);
    render(<I18nProvider><Probe /></I18nProvider>);
    await userEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByTestId("locale")).toHaveTextContent("id");
  });
});
