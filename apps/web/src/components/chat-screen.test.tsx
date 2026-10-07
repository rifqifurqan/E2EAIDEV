import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatScreen } from "./chat-screen";
import { I18nProvider } from "@/i18n/context";

function renderChat(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <ChatScreen />
    </I18nProvider>,
  );
}

describe("ChatScreen", () => {
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
});
