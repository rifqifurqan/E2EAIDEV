import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanScreen } from "./plan-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  createUseCase: vi.fn(),
  classifyBotRisk: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderPlan(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <PlanScreen />
    </I18nProvider>,
  );
}

async function fillRequired() {
  await userEvent.type(screen.getByLabelText(/use-case title/i), "HR assistant");
  await userEvent.type(screen.getByLabelText(/problem/i), "Answer HR policy questions");
  await userEvent.type(screen.getByLabelText(/^users/i), "HR staff, Employees");
  await userEvent.type(screen.getByLabelText(/task success/i), "85% answered correctly");
  await userEvent.type(screen.getByLabelText(/deflection/i), "30% fewer tickets");
  await userEvent.type(screen.getByLabelText(/time saved/i), "10 min per question");
}

describe("PlanScreen", () => {
  beforeEach(() => {
    apiMock.createUseCase.mockReset();
    apiMock.classifyBotRisk.mockReset();
  });

  it("submits the intake with real success metrics, users, sources and systems", async () => {
    apiMock.createUseCase.mockResolvedValueOnce({ id: "uc1", title: "HR assistant", status: "submitted" });
    renderPlan();
    await fillRequired();
    await userEvent.type(screen.getByLabelText(/data sources/i), "HR handbook; Leave policy");
    await userEvent.type(screen.getByLabelText(/systems to integrate/i), "Talenta, SAP");
    await userEvent.click(screen.getByRole("button", { name: /submit use case/i }));
    expect(apiMock.createUseCase).toHaveBeenCalledWith({
      title: "HR assistant",
      problem: "Answer HR policy questions",
      users: ["HR staff", "Employees"],
      success_metrics: {
        task_success: "85% answered correctly",
        deflection: "30% fewer tickets",
        time_saved: "10 min per question",
      },
      data_sources: ["HR handbook", "Leave policy"],
      systems_to_integrate: ["Talenta", "SAP"],
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/submitted/i);
  });

  it("does not submit while a required field is empty", async () => {
    renderPlan();
    await userEvent.type(screen.getByLabelText(/use-case title/i), "HR assistant");
    await userEvent.click(screen.getByRole("button", { name: /submit use case/i }));
    expect(apiMock.createUseCase).not.toHaveBeenCalled();
  });

  it("shows a generic localized error without server text", async () => {
    apiMock.createUseCase.mockRejectedValueOnce(new Error("SQL boom password=abc"));
    renderPlan();
    await fillRequired();
    await userEvent.click(screen.getByRole("button", { name: /submit use case/i }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not submit/i);
    expect(alert).not.toHaveTextContent(/boom|password/i);
  });

  it("submits a bot risk classification with safe governance fields", async () => {
    apiMock.classifyBotRisk.mockResolvedValueOnce({
      bot_id: "11111111-1111-1111-1111-111111111111",
      eu_ai_act_tier: "high",
      pdp_impact_level: "personal_data",
    });
    renderPlan();

    await userEvent.type(screen.getByLabelText(/risk bot id/i), "11111111-1111-1111-1111-111111111111");
    await userEvent.selectOptions(screen.getByLabelText(/eu ai act tier/i), "high");
    await userEvent.type(screen.getByLabelText(/nist govern/i), "mapped");
    await userEvent.type(screen.getByLabelText(/nist measure/i), "required");
    await userEvent.type(screen.getByLabelText(/uu pdp data impact/i), "Processes employee leave and identity data");
    await userEvent.click(screen.getByRole("button", { name: /classify risk/i }));

    expect(apiMock.classifyBotRisk).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111", {
      eu_ai_act_tier: "high",
      nist_ai_rmf_profile: { govern: "mapped", measure: "required" },
      uu_pdp_data_impact: "Processes employee leave and identity data",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/risk classified.*high/i);
  });

  it("shows a generic localized risk-classification error without server text", async () => {
    apiMock.classifyBotRisk.mockRejectedValueOnce(new Error("Bot not found token=abc"));
    renderPlan();

    await userEvent.type(screen.getByLabelText(/risk bot id/i), "11111111-1111-1111-1111-111111111111");
    await userEvent.type(screen.getByLabelText(/uu pdp data impact/i), "No personal data");
    await userEvent.click(screen.getByRole("button", { name: /classify risk/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not classify/i);
    expect(alert).not.toHaveTextContent(/token|not found/i);
  });

  it("renders in Indonesian with the why-it-matters panel", async () => {
    renderPlan("id");
    expect(screen.getByLabelText(/judul kasus penggunaan/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /kirim kasus penggunaan/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /mengapa penting/i })).toBeInTheDocument();
  });
});
