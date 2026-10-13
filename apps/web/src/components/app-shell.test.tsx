import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppShell } from "./app-shell";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  login: vi.fn(),
  me: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: apiMock,
}));

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
  beforeEach(() => {
    apiMock.login.mockReset();
    apiMock.me.mockReset();
    apiMock.me.mockRejectedValue(new Error("not authenticated"));
  });

  it("restores the signed-in state on load when a session cookie is already valid", async () => {
    apiMock.me.mockReset();
    apiMock.me.mockResolvedValue({ user_id: "u1", email: "andi@demo.e2eai", display_name: "Andi" });
    renderShell();
    expect(await screen.findByText(/signed in as andi@demo\.e2eai/i)).toBeInTheDocument();
  });

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

  it("provides a keyboard skip link to the main content", () => {
    renderShell();
    const skipLink = screen.getByRole("link", { name: /skip to main content/i });
    const main = screen.getByRole("main");
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(main).toHaveAttribute("id", "main-content");
    expect(main).toHaveAttribute("tabIndex", "-1");
  });

  it("localizes the feature navigation landmark label", () => {
    renderShell("id");
    expect(screen.getByRole("navigation", { name: /fitur/i })).toBeInTheDocument();
  });

  it("has banner landmark for header", () => {
    renderShell();
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it("lets a user sign in from the shell header", async () => {
    apiMock.login.mockResolvedValueOnce({ user_id: "u1", csrf_token: "csrf" });
    renderShell();
    await userEvent.type(screen.getByLabelText(/email/i), "admin@local");
    await userEvent.type(screen.getByLabelText(/password/i), "secret-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(apiMock.login).toHaveBeenCalledWith({ email: "admin@local", password: "secret-password" });
    expect(await screen.findByText(/signed in/i)).toBeInTheDocument();
  });
});
