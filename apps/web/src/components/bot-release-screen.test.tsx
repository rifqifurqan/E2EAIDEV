import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BotReleaseScreen } from "./bot-release-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listBotApprovals: vi.fn(),
  listBotApprovalsPage: vi.fn(),
  decideBotApproval: vi.fn(),
  requestBotApproval: vi.fn(),
  createBot: vi.fn(),
  grantBotAccess: vi.fn(),
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
    apiMock.listBotApprovalsPage.mockReset();
    apiMock.listBotApprovals.mockResolvedValue({ items: [], next_cursor: null });
    apiMock.decideBotApproval.mockReset();
    apiMock.requestBotApproval.mockReset();
    apiMock.createBot.mockReset();
    apiMock.grantBotAccess.mockReset();
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
  const approval = (id: string, status: string) => ({
    id,
    bot_id: "b1",
    approval_type: "high_risk_release",
    risk_tier: "high",
    status,
    rationale: null,
    decision_note: null,
    requested_by: "u1",
    decided_by: null,
    created_at: "2026-10-14T00:00:00+00:00",
    decided_at: null,
  });

  it("approves a pending request and refreshes the list", async () => {
    const user = userEvent.setup();
    apiMock.listBotApprovals.mockResolvedValue({ items: [approval("a1", "pending")], next_cursor: null });
    apiMock.decideBotApproval.mockResolvedValue(approval("a1", "approved"));
    renderBots();
    await screen.findByText("high_risk_release");
    apiMock.listBotApprovals.mockResolvedValue({ items: [approval("a1", "approved")], next_cursor: null });
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    await waitFor(() => expect(apiMock.decideBotApproval).toHaveBeenCalledWith("a1", "approved"));
    expect(await screen.findByText("approved")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
  });

  it("rejects a pending request", async () => {
    const user = userEvent.setup();
    apiMock.listBotApprovals.mockResolvedValue({ items: [approval("a2", "pending")], next_cursor: null });
    apiMock.decideBotApproval.mockResolvedValue(approval("a2", "rejected"));
    renderBots();
    await screen.findByText("high_risk_release");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    await waitFor(() => expect(apiMock.decideBotApproval).toHaveBeenCalledWith("a2", "rejected"));
  });

  it("offers no decision buttons for already decided requests", async () => {
    apiMock.listBotApprovals.mockResolvedValue({ items: [approval("a3", "approved")], next_cursor: null });
    renderBots();
    await screen.findByText("approved");
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when the decision fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listBotApprovals.mockResolvedValue({ items: [approval("a4", "pending")], next_cursor: null });
    apiMock.decideBotApproval.mockRejectedValue(new ApiError(409, "Approval request already decided", "stack detail"));
    renderBots();
    await screen.findByText("high_risk_release");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    expect(await screen.findByText(/could not record the decision/i)).toBeInTheDocument();
    expect(screen.queryByText(/stack detail/i)).not.toBeInTheDocument();
  });

  it("labels the decision buttons in Indonesian", async () => {
    apiMock.listBotApprovals.mockResolvedValue({ items: [approval("a5", "pending")], next_cursor: null });
    renderBots("id");
    expect(await screen.findByRole("button", { name: /^setujui$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^tolak$/i })).toBeInTheDocument();
  });

  const BOT_ID = "3f2c8a52-1b7e-4c1d-9a55-0d2f6a9b7c11";

  it("requests an approval for a bot id with an optional rationale and reloads", async () => {
    const user = userEvent.setup();
    apiMock.requestBotApproval.mockResolvedValue(approval("n1", "pending"));
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    await user.type(screen.getByLabelText(/bot id/i), BOT_ID);
    await user.type(screen.getByLabelText(/rationale/i), "Handles HR data");
    await user.click(screen.getByRole("button", { name: /request approval/i }));
    await waitFor(() => expect(apiMock.requestBotApproval).toHaveBeenCalledWith(BOT_ID, "Handles HR data"));
    await waitFor(() => expect(apiMock.listBotApprovals).toHaveBeenCalledTimes(2));
  });

  it("omits a blank rationale and disables request until the bot id is a UUID", async () => {
    const user = userEvent.setup();
    apiMock.requestBotApproval.mockResolvedValue(approval("n2", "pending"));
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    const button = screen.getByRole("button", { name: /request approval/i });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText(/bot id/i), "nope");
    expect(button).toBeDisabled();
    await user.clear(screen.getByLabelText(/bot id/i));
    await user.type(screen.getByLabelText(/bot id/i), BOT_ID);
    await user.click(button);
    await waitFor(() => expect(apiMock.requestBotApproval).toHaveBeenCalledWith(BOT_ID, undefined));
  });

  it("shows a generic error without server text when the request fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.requestBotApproval.mockRejectedValue(new ApiError(404, "Bot not found", "stack detail"));
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    await user.type(screen.getByLabelText(/bot id/i), BOT_ID);
    await user.click(screen.getByRole("button", { name: /request approval/i }));
    expect(await screen.findByText(/could not request the approval/i)).toBeInTheDocument();
    expect(screen.queryByText(/stack detail/i)).not.toBeInTheDocument();
  });

  it("labels the request form in Indonesian", async () => {
    renderBots("id");
    expect(await screen.findByRole("button", { name: /minta persetujuan/i })).toBeInTheDocument();
  });

  it("creates a bot from the New Bot form and prefills the approval bot id", async () => {
    const user = userEvent.setup();
    apiMock.createBot.mockResolvedValue({ id: BOT_ID, name: "HR assistant" });
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    expect(screen.queryByLabelText(/bot name/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^new bot$/i }));
    const create = screen.getByRole("button", { name: /^create bot$/i });
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText(/bot name/i), "  HR assistant ");
    await user.click(create);
    await waitFor(() => expect(apiMock.createBot).toHaveBeenCalledWith("HR assistant"));
    expect(await screen.findByRole("status")).toHaveTextContent(/bot created.*HR assistant/i);
    expect(screen.getByLabelText(/^bot id/i)).toHaveValue(BOT_ID);
  });

  it("shows a generic error without server text when bot creation fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.createBot.mockRejectedValue(new ApiError(403, "Forbidden", "secret scope detail"));
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    await user.click(screen.getByRole("button", { name: /^new bot$/i }));
    await user.type(screen.getByLabelText(/bot name/i), "X");
    await user.click(screen.getByRole("button", { name: /^create bot$/i }));
    expect(await screen.findByText(/could not create the bot/i)).toBeInTheDocument();
    expect(screen.queryByText(/secret scope detail/i)).not.toBeInTheDocument();
  });

  it("labels the New Bot form in Indonesian", async () => {
    const user = userEvent.setup();
    renderBots("id");
    await user.click(await screen.findByRole("button", { name: /^bot baru$/i }));
    expect(screen.getByLabelText(/nama bot/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^buat bot$/i })).toBeInTheDocument();
  });

  it("grants a principal access to a bot with level user", async () => {
    const user = userEvent.setup();
    apiMock.grantBotAccess.mockResolvedValue({ principal: "team:t1", level: "user" });
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    await user.type(screen.getByLabelText(/target bot/i), BOT_ID);
    await user.type(screen.getByLabelText(/principal/i), " team:t1 ");
    await user.click(screen.getByRole("button", { name: /^grant access$/i }));
    await waitFor(() => expect(apiMock.grantBotAccess).toHaveBeenCalledWith(BOT_ID, { principal: "team:t1", level: "user" }));
    expect(await screen.findByText(/access granted.*team:t1/i)).toBeInTheDocument();
  });

  it("disables grant until the bot is a UUID and the principal has a known type prefix", async () => {
    const user = userEvent.setup();
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    const button = screen.getByRole("button", { name: /^grant access$/i });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText(/target bot/i), BOT_ID);
    await user.type(screen.getByLabelText(/principal/i), "nobody");
    expect(button).toBeDisabled();
    await user.clear(screen.getByLabelText(/principal/i));
    await user.type(screen.getByLabelText(/principal/i), "division:d1");
    expect(button).toBeEnabled();
  });

  it("shows a generic error without server text when the grant fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.grantBotAccess.mockRejectedValue(new ApiError(404, "Bot not found", "stack detail"));
    renderBots();
    await screen.findByText(/no approval requests yet/i);
    await user.type(screen.getByLabelText(/target bot/i), BOT_ID);
    await user.type(screen.getByLabelText(/principal/i), "user:u1");
    await user.click(screen.getByRole("button", { name: /^grant access$/i }));
    expect(await screen.findByText(/could not grant access/i)).toBeInTheDocument();
    expect(screen.queryByText(/stack detail/i)).not.toBeInTheDocument();
  });

  it("prefills the grant target bot after creating a bot, and labels the grant form in Indonesian", async () => {
    const user = userEvent.setup();
    apiMock.createBot.mockResolvedValue({ id: BOT_ID, name: "HR assistant" });
    renderBots("id");
    await screen.findByText(/belum ada permintaan persetujuan/i);
    await user.click(screen.getByRole("button", { name: /^bot baru$/i }));
    await user.type(screen.getByLabelText(/nama bot/i), "HR assistant");
    await user.click(screen.getByRole("button", { name: /^buat bot$/i }));
    await screen.findByRole("status");
    expect(screen.getByLabelText(/bot target/i)).toHaveValue(BOT_ID);
    expect(screen.getByRole("button", { name: /^beri akses$/i })).toBeInTheDocument();
  });

  it("loads more approval requests with the next cursor", async () => {
    const user = userEvent.setup();
    apiMock.listBotApprovals.mockResolvedValue({ items: [{ ...approval("m1", "approved"), approval_type: "type_page_one" }], next_cursor: "cur-2" });
    apiMock.listBotApprovalsPage.mockResolvedValue({ items: [{ ...approval("m2", "approved"), approval_type: "type_page_two" }], next_cursor: null });
    renderBots();
    await screen.findByText("type_page_one");
    await user.click(screen.getByRole("button", { name: /load more/i }));
    expect(await screen.findByText("type_page_two")).toBeInTheDocument();
    expect(apiMock.listBotApprovalsPage).toHaveBeenCalledWith("cur-2");
    expect(screen.getByText("type_page_one")).toBeInTheDocument();
  });
});
