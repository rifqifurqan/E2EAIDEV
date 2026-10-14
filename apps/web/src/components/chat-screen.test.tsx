import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatScreen } from "./chat-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  ask: vi.fn(),
  createConversation: vi.fn(),
  listConversations: vi.fn(),
  listMessages: vi.fn(),
  sendMessage: vi.fn(),
  recordFeedback: vi.fn(),
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
    apiMock.listConversations.mockReset();
    apiMock.listConversations.mockResolvedValue({ conversations: [], next_cursor: null });
    apiMock.listMessages.mockReset();
    apiMock.listMessages.mockResolvedValue({ messages: [] });
    apiMock.sendMessage.mockReset();
    apiMock.recordFeedback.mockReset();
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
    apiMock.createConversation.mockResolvedValue({ id: "c1", title: "How many leave days?", created_at: "n", updated_at: "n" });
    apiMock.sendMessage.mockResolvedValueOnce({
      message_id: "m1",
      answer: "Policy says 12 days.",
      citations: [{ document_id: "doc1", version_id: "v1", chunk_id: "c1", page: 2, section: "Leave" }],
    });
    renderChat();
    await userEvent.type(screen.getByRole("textbox", { name: /ask/i }), "How many leave days?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(apiMock.createConversation).toHaveBeenCalledWith("How many leave days?");
    expect(apiMock.sendMessage).toHaveBeenCalledWith("c1", "How many leave days?", "all", undefined);
    expect(await screen.findByText(/policy says 12 days/i)).toBeInTheDocument();
    expect(screen.getByText(/doc1/i)).toBeInTheDocument();
  });

  it("renders citations in the shape the live API returns (document name, page)", async () => {
    apiMock.createConversation.mockResolvedValue({ id: "c1", title: "Leave days?", created_at: "n", updated_at: "n" });
    apiMock.sendMessage.mockResolvedValueOnce({
      message_id: "m1",
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
    expect(await screen.findByText(/new conversation/i, { selector: "li button" })).toBeInTheDocument();
    expect(screen.queryByText(/conv1/i)).not.toBeInTheDocument();
  });

  it("lists saved conversations by title (not id) and loads one's history on click (UAT-CHAT-001/004)", async () => {
    apiMock.listConversations.mockResolvedValue({
      conversations: [{ id: "11111111-2222-3333-4444-555555555555", title: "Leave policy", created_at: "n", updated_at: "n" }],
      next_cursor: null,
    });
    apiMock.listMessages.mockResolvedValue({
      messages: [
        { id: "m1", role: "user", content: "How many days?", stop_reason: null, created_at: "n", citations: [] },
        { id: "m2", role: "assistant", content: "12 days.", stop_reason: null, created_at: "n", citations: [{ document: "leave.txt", page: 1, section: null }] },
      ],
    });
    renderChat();
    const item = await screen.findByRole("button", { name: "Leave policy" });
    expect(screen.queryByText(/11111111-2222/)).not.toBeInTheDocument();
    await userEvent.click(item);
    expect(apiMock.listMessages).toHaveBeenCalledWith("11111111-2222-3333-4444-555555555555");
    expect(await screen.findByText("12 days.")).toBeInTheDocument();
    expect(screen.getByText(/leave\.txt/)).toBeInTheDocument();
  });

  it("keeps asking inside the same conversation instead of creating a new one each time", async () => {
    apiMock.createConversation.mockResolvedValue({ id: "c1", title: "Q1", created_at: "n", updated_at: "n" });
    apiMock.sendMessage.mockResolvedValue({ message_id: "m", answer: "A", citations: [] });
    renderChat();
    const box = screen.getByRole("textbox", { name: /ask/i });
    await userEvent.type(box, "Q1");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findAllByText("A");
    await userEvent.type(box, "Q2");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(apiMock.sendMessage).toHaveBeenCalledTimes(2));
    expect(apiMock.createConversation).toHaveBeenCalledTimes(1);
    expect(apiMock.sendMessage).toHaveBeenLastCalledWith("c1", "Q2", "all", undefined);
  });

  it("thumbs buttons send feedback for the latest assistant message (UAT-CHAT-003)", async () => {
    apiMock.createConversation.mockResolvedValue({ id: "c1", title: "Q", created_at: "n", updated_at: "n" });
    apiMock.sendMessage.mockResolvedValue({ message_id: "msg-42", answer: "A", citations: [] });
    apiMock.recordFeedback.mockResolvedValue({ status: "ok", rating: "up" });
    renderChat();
    await userEvent.type(screen.getByRole("textbox", { name: /ask/i }), "Q");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findAllByText("A");
    await userEvent.click(screen.getByRole("button", { name: /^yes$/i }));
    expect(apiMock.recordFeedback).toHaveBeenCalledWith("msg-42", { rating: "up" });
    expect(await screen.findByText(/thanks for your feedback/i)).toBeInTheDocument();
  });
});
