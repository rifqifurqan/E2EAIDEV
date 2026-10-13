import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BotReleaseScreen } from "./bot-release-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listBotApprovals: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderBots(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <BotReleaseScreen />
    </I18nProvider>,
  );
}

describe("BotReleaseScreen", () => {
  beforeEach(() => {
    apiMock.listBotApprovals.mockReset();
    apiMock.listBotApprovals.mockResolvedValue({ items: [], next_cursor: null });
  });

  it("lists bot approval requests with risk tier and status", async () => {
    apiMock.listBotApprovals.mockResolvedValue({
      items: [
        {
          id: "a1",
          bot_id: "b1",
          approval_type: "high_risk_release",
          risk_tier: "high",
          status: "pending",
          rationale: null,
          decision_note: null,
          requested_by: "u1",
          decided_by: null,
          created_at: "2026-10-14T00:00:00+00:00",
          decided_at: null,
        },
      ],
      next_cursor: null,
    });
    renderBots();
    expect(await screen.findByText("high_risk_release")).toBeInTheDocument();
    expect(screen.getByText(/risk: high/i)).toBeInTheDocument();
    expect(screen.getByText(/pending/i)).toBeInTheDocument();
  });

  it("shows an empty approvals state", async () => {
    renderBots();
    expect(await screen.findByText(/no approval requests/i)).toBeInTheDocument();
  });

  it("shows a sign-in notice on 401", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listBotApprovals.mockRejectedValue(new ApiError(401, "Unauthorized"));
    renderBots();
    expect(await screen.findByRole("alert")).toHaveTextContent(/sign in/i);
  });

  it("shows approvals empty state in Indonesian", async () => {
    renderBots("id");
    expect(await screen.findByText(/belum ada permintaan persetujuan/i)).toBeInTheDocument();
  });

  it("renders bundles, grants, scope sections", () => {
    renderBots();
    expect(screen.getByText(/bundles/i)).toBeInTheDocument();
    expect(screen.getByText(/access grants/i)).toBeInTheDocument();
    expect(screen.getByText(/knowledge scope/i)).toBeInTheDocument();
  });

  it("renders rollback and release buttons", () => {
    renderBots();
    expect(screen.getByRole("button", { name: /rollback/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /release bundle/i })).toBeInTheDocument();
  });

  it("renders new bot button", () => {
    renderBots();
    expect(screen.getByRole("button", { name: /new bot/i })).toBeInTheDocument();
  });

  it("renders in Indonesian", () => {
    renderBots("id");
    expect(screen.getByRole("button", { name: /kembalikan/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rilis bundel/i })).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderBots();
    expect(screen.getByRole("heading", { name: /bot release/i })).toBeInTheDocument();
  });
});
