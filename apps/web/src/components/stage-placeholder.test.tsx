import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StagePlaceholder } from "./stage-placeholder";
import { I18nProvider } from "@/i18n/context";

type StageKey = "plan" | "data" | "build" | "test" | "release" | "operate" | "improve";

const STAGES: StageKey[] = ["plan", "data", "build", "test", "release", "operate", "improve"];

function renderStage(stage: StageKey, locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <StagePlaceholder stage={stage} />
    </I18nProvider>,
  );
}

describe("StagePlaceholder", () => {
  it("renders a why-it-matters panel on every lifecycle stage", () => {
    for (const stage of STAGES) {
      const { unmount } = renderStage(stage);
      expect(screen.getByRole("region", { name: /why it matters/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /owasp/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /nist/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /eu ai act/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /iso.*42001/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /uu pdp/i })).toBeInTheDocument();
      unmount();
    }
  });

  it("renders the panel in Indonesian", () => {
    renderStage("operate", "id");
    expect(screen.getByRole("region", { name: /mengapa penting/i })).toBeInTheDocument();
    expect(screen.getByText(/pemantauan berkelanjutan/i)).toBeInTheDocument();
  });
});
