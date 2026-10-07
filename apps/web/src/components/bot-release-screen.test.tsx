import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BotReleaseScreen } from "./bot-release-screen";
import { I18nProvider } from "@/i18n/context";

function renderBots(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <BotReleaseScreen />
    </I18nProvider>,
  );
}

describe("BotReleaseScreen", () => {
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
