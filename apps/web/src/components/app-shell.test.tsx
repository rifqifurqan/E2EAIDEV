import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppShell } from "./app-shell";
import { I18nProvider } from "@/i18n/context";

function renderShell(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <AppShell>
        <div data-testid="page-content">Page</div>
      </AppShell>
    </I18nProvider>,
  );
}

describe("AppShell", () => {
  it("renders lifecycle nav with all 7 stages in order", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: /lifecycle/i });
    const links = within(nav).getAllByRole("link");
    const labels = links.map((l) => l.textContent);
    expect(labels).toEqual([
      "Plan",
      "Data",
      "Build",
      "Test",
      "Release",
      "Operate",
      "Improve",
    ]);
  });

  it("renders lifecycle nav in Indonesian", () => {
    renderShell("id");
    const nav = screen.getByRole("navigation", { name: /siklus/i });
    const links = within(nav).getAllByRole("link");
    const labels = links.map((l) => l.textContent);
    expect(labels).toEqual([
      "Perencanaan",
      "Data",
      "Pembangunan",
      "Pengujian",
      "Rilis",
      "Operasi",
      "Peningkatan",
    ]);
  });

  it("renders sidebar nav with feature links", () => {
    renderShell();
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Admin" })).toBeInTheDocument();
  });

  it("renders language switch button", () => {
    renderShell();
    const btn = screen.getByRole("button", { name: /bahasa indonesia/i });
    expect(btn).toBeInTheDocument();
  });

  it("switches language when button is clicked", async () => {
    renderShell();
    const btn = screen.getByRole("button", { name: /bahasa indonesia/i });
    await userEvent.click(btn);
    // After switching to ID, button should show "English"
    expect(
      screen.getByRole("button", { name: /english/i }),
    ).toBeInTheDocument();
    // Nav should show Indonesian labels
    expect(screen.getByRole("link", { name: "Dokumen" })).toBeInTheDocument();
  });

  it("renders main content area with landmark", () => {
    renderShell();
    const main = screen.getByRole("main");
    expect(main).toBeInTheDocument();
    expect(within(main).getByTestId("page-content")).toBeInTheDocument();
  });

  it("has banner landmark for header", () => {
    renderShell();
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });
});
