import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatScreen } from "./chat-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  ask: vi.fn(),
  createConversation: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: apiMock,
}));

function renderChat(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <ChatScreen />
    </I18nProvider>,
  );
}

describe("ChatScreen", () => {
  beforeEach(() => {
    apiMock.ask.mockReset();
    apiMock.createConversation.mockReset();
  });

  it("renders conversation list area", () => {
    renderChat();
    expect(screen.getByRole("region", { name: /conversations/i })).toBeInTheDocument();
  });

  it("renders new conversation button", () => {
    renderChat();
    expect(screen.getByRole("button", { name: /new conversation/i })).toBeInTheDocument();
  });

  it("renders scope picker", () => {
    renderChat();
    expect(screen.getByRole("combobox", { name: /scope/i })).toBeInTheDocument();
  });

  it("renders message input", () => {
    renderChat();
    expect(screen.getByRole("textbox", { name: /ask/i })).toBeInTheDocument();
  });

  it("renders stop button", () => {
    renderChat();
    expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();
  });

  it("renders feedback buttons", () => {
    renderChat();
    expect(screen.getByRole("button", { name: /yes/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /no$/i })).toBeInTheDocument();
  });

  it("renders citations area", () => {
    renderChat();
    expect(screen.getByRole("region", { name: /citations/i })).toBeInTheDocument();
  });

  it("renders in Indonesian", () => {
    renderChat("id");
    expect(screen.getByRole("button", { name: /percakapan baru/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /berhenti/i })).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderChat();
    expect(screen.getByRole("heading", { name: /chat/i })).toBeInTheDocument();
  });

  it("sends a typed question to the chat API and renders the answer", async () => {
    apiMock.ask.mockResolvedValueOnce({
      answer: "Policy says 12 days.",
      citations: [{ document_id: "doc1", version_id: "v1", chunk_id: "c1", page: 2, section: "Leave" }],
    });
    renderChat();
    await userEvent.type(screen.getByRole("textbox", { name: /ask/i }), "How many leave days?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(apiMock.ask).toHaveBeenCalledWith("How many leave days?", "all", undefined);
    expect(await screen.findByText(/policy says 12 days/i)).toBeInTheDocument();
    expect(screen.getByText(/doc1/i)).toBeInTheDocument();
  });

  it("renders citations in the shape the live API returns (document name, page)", async () => {
    apiMock.ask.mockResolvedValueOnce({
      answer: "Employees receive 12 days.",
      citations: [{ document: "leave-policy.txt", page: 1, section: "" }],
    });
    renderChat();
    await userEvent.type(screen.getByRole("textbox", { name: /ask/i }), "Leave days?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    const region = await screen.findByRole("region", { name: /citations/i });
    expect(await within(region).findByText(/leave-policy\.txt/i)).toBeInTheDocument();
    expect(within(region).getByText(/page 1/i)).toBeInTheDocument();
  });

  it("creates a new conversation from the button", async () => {
    apiMock.createConversation.mockResolvedValueOnce({ id: "conv1", title: "New Conversation", created_at: "now", updated_at: "now" });
    renderChat();
    await userEvent.click(screen.getByRole("button", { name: /new conversation/i }));
    expect(apiMock.createConversation).toHaveBeenCalledWith("New Conversation");
    expect(await screen.findByText(/conv1/i)).toBeInTheDocument();
  });
});
