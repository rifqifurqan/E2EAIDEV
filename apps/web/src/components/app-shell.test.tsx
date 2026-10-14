import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppShell } from "./app-shell";
import { I18nProvider } from "@/i18n/context";
import { SESSION_EXPIRED_EVENT } from "@/lib/api-client";
import { act } from "@testing-library/react";
import { useEffect } from "react";

const apiMock = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: apiMock,
  SESSION_EXPIRED_EVENT: "e2eai:session-expired",
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
    apiMock.logout.mockReset();
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
    const nav = screen.getByRole("navigation", { name: /^features$/i });
    expect(within(nav).getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Chat" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Admin" })).toBeInTheDocument();
  });

  it("keeps feature navigation reachable on mobile widths (UAT-NAV-001)", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: /mobile feature navigation/i });
    expect(nav).toHaveClass("md:hidden");
    expect(nav).not.toHaveClass("hidden");
    expect(within(nav).getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Chat" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Admin" })).toBeInTheDocument();
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
    // Both desktop and mobile feature navs should show Indonesian labels.
    expect(screen.getAllByRole("link", { name: "Dokumen" }).length).toBeGreaterThanOrEqual(2);
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
    expect(screen.getByRole("navigation", { name: /^Fitur$/i })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /fitur seluler/i })).toBeInTheDocument();
  });

  it("has banner landmark for header", () => {
    renderShell();
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it("lets a user sign in from the shell header", async () => {
    apiMock.login.mockResolvedValueOnce({ user_id: "u1", csrf_token: "csrf" });
    renderShell();
    await userEvent.type(screen.getByLabelText(/email/i), "admin@local.e2eai");
    await userEvent.type(screen.getByLabelText(/password/i), "secret-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(apiMock.login).toHaveBeenCalledWith({ email: "admin@local.e2eai", password: "secret-password" });
    expect(await screen.findByText(/signed in/i)).toBeInTheDocument();
  });

  it("hides the sign-in form once signed in and offers Sign out (UAT-AUTH-001)", async () => {
    apiMock.login.mockResolvedValueOnce({ user_id: "u1", csrf_token: "csrf-1" });
    renderShell();
    await userEvent.type(screen.getByLabelText(/email/i), "andi@demo.e2eai");
    await userEvent.type(screen.getByLabelText(/password/i), "secret-password");
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    expect(await screen.findByText(/signed in as andi@demo\.e2eai/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sign in$/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("signs out with the CSRF token from the restored session and shows the form again", async () => {
    apiMock.me.mockReset();
    apiMock.me.mockResolvedValue({ user_id: "u1", email: "andi@demo.e2eai", display_name: "Andi", csrf_token: "csrf-from-me" });
    apiMock.logout.mockResolvedValueOnce({ status: "ok" });
    renderShell();
    await userEvent.click(await screen.findByRole("button", { name: /sign out/i }));
    expect(apiMock.logout).toHaveBeenCalledWith("csrf-from-me");
    expect(await screen.findByRole("button", { name: /^sign in$/i })).toBeInTheDocument();
    expect(screen.queryByText(/signed in as/i)).not.toBeInTheDocument();
  });

  it("localizes the signed-in status and sign-out in Indonesian", async () => {
    apiMock.me.mockReset();
    apiMock.me.mockResolvedValue({ user_id: "u1", email: "andi@demo.e2eai", display_name: "Andi", csrf_token: "c" });
    renderShell("id");
    expect(await screen.findByText(/masuk sebagai andi@demo\.e2eai/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /keluar/i })).toBeInTheDocument();
  });

  it("drops the signed-in header and explains when the session expires mid-use (UAT-AUTH-002)", async () => {
    apiMock.me.mockReset();
    apiMock.me.mockResolvedValue({ user_id: "u1", email: "andi@demo.e2eai", display_name: "Andi" });
    renderShell();
    expect(await screen.findByText(/signed in as andi@demo\.e2eai/i)).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });
    expect(screen.queryByText(/signed in as/i)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Email")).toBeInTheDocument();
    expect(screen.getByText(/session expired/i)).toBeInTheDocument();
  });

  it("reloads the page content after signing in again so stale 'please sign in' states clear", async () => {
    let mounts = 0;
    function Probe() {
      useEffect(() => {
        mounts += 1;
      }, []);
      return <div>probe</div>;
    }
    apiMock.login.mockResolvedValue({ user_id: "u1", csrf_token: "c" });
    render(
      <I18nProvider defaultLocale="en">
        <AppShell>
          <Probe />
        </AppShell>
      </I18nProvider>,
    );
    expect(mounts).toBe(1);
    await userEvent.type(screen.getByPlaceholderText("Email"), "andi@demo.e2eai");
    await userEvent.type(screen.getByPlaceholderText("Password"), "pw");
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    expect(await screen.findByText(/signed in as andi@demo\.e2eai/i)).toBeInTheDocument();
    expect(mounts).toBe(2);
  });
});
