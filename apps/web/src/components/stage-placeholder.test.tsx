import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StagePlaceholder } from "./stage-placeholder";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  createUseCase: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: apiMock,
}));

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
  beforeEach(() => {
    apiMock.createUseCase.mockReset();
  });

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

  it("renders and submits the Plan use-case intake form", async () => {
    apiMock.createUseCase.mockResolvedValueOnce({ id: "uc1", title: "HR assistant", status: "submitted" });
    renderStage("plan");
    await userEvent.type(screen.getByLabelText(/use-case title/i), "HR assistant");
    await userEvent.type(screen.getByLabelText(/business owner/i), "Nina");
    await userEvent.type(screen.getByLabelText(/purpose/i), "Answer HR policy questions");
    await userEvent.click(screen.getByRole("button", { name: /submit use case/i }));
    expect(apiMock.createUseCase).toHaveBeenCalledWith({
      title: "HR assistant",
      business_owner: "Nina",
      purpose: "Answer HR policy questions",
      risk_tier: "limited",
    });
    expect(await screen.findByText(/submitted/i)).toBeInTheDocument();
  });
});
