import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BuildScreen } from "./build-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listModels: vi.fn(),
  decideModel: vi.fn(),
  registerModel: vi.fn(),
  attachEvalRun: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderBuild(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <BuildScreen />
    </I18nProvider>,
  );
}

describe("BuildScreen", () => {
  beforeEach(() => {
    apiMock.listModels.mockReset();
    apiMock.decideModel.mockReset();
    apiMock.registerModel.mockReset();
    apiMock.attachEvalRun.mockReset();
  });

  it("lists registered model versions with approval status", async () => {
    apiMock.listModels.mockResolvedValue({
      models: [
        {
          name: "support-llm",
          version: "v2",
          parent_version: "v1",
          lineage: {},
          eval_scores: {},
          approval_status: "approved",
          approved_by: null,
        },
      ],
      next_cursor: null,
    });
    renderBuild();
    expect(await screen.findByText("support-llm")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText(/approved/i)).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    renderBuild();
    expect(await screen.findByText(/no model versions registered/i)).toBeInTheDocument();
  });

  it("shows a sign-in notice on 401", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listModels.mockRejectedValue(new ApiError(401, "Unauthorized"));
    renderBuild();
    expect(await screen.findByRole("alert")).toHaveTextContent(/sign in/i);
  });

  it("renders in Indonesian", async () => {
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    renderBuild("id");
    expect(await screen.findByText(/belum ada versi model/i)).toBeInTheDocument();
  });
  const models = (status: string, scores: Record<string, number>) => ({
    models: [
      { name: "support-llm", version: "v3", parent_version: null, lineage: {}, eval_scores: scores, approval_status: status, approved_by: null },
    ],
    next_cursor: null,
  });

  it("approves a pending model version that has eval scores and reloads", async () => {
    const user = userEvent.setup();
    apiMock.listModels.mockResolvedValue(models("pending", { answer_correctness: 0.9 }));
    apiMock.decideModel.mockResolvedValue({});
    renderBuild();
    await screen.findByText("support-llm");
    apiMock.listModels.mockResolvedValue(models("approved", { answer_correctness: 0.9 }));
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    await waitFor(() => expect(apiMock.decideModel).toHaveBeenCalledWith("support-llm", "v3", "approved"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument());
  });

  it("disables approve when the version has no eval score, but still allows reject", async () => {
    const user = userEvent.setup();
    apiMock.listModels.mockResolvedValue(models("pending", {}));
    apiMock.decideModel.mockResolvedValue({});
    renderBuild();
    await screen.findByText("support-llm");
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeDisabled();
    expect(screen.getByText(/needs an eval score/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    await waitFor(() => expect(apiMock.decideModel).toHaveBeenCalledWith("support-llm", "v3", "rejected"));
  });

  it("offers no decision buttons for already decided versions", async () => {
    apiMock.listModels.mockResolvedValue(models("approved", { a: 1 }));
    renderBuild();
    await screen.findByText("support-llm");
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when the decision fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listModels.mockResolvedValue(models("pending", { a: 1 }));
    apiMock.decideModel.mockRejectedValue(new ApiError(403, "Not allowed", "internal detail"));
    renderBuild();
    await screen.findByText("support-llm");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    expect(await screen.findByText(/could not record the decision/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels the decision buttons in Indonesian", async () => {
    apiMock.listModels.mockResolvedValue(models("pending", { a: 1 }));
    renderBuild("id");
    expect(await screen.findByRole("button", { name: /^setujui$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^tolak$/i })).toBeInTheDocument();
  });
  it("registers a model version with an optional parent and reloads the list", async () => {
    const user = userEvent.setup();
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    apiMock.registerModel.mockResolvedValue({});
    renderBuild();
    await screen.findByText(/no model versions registered yet/i);
    apiMock.listModels.mockResolvedValue(models("pending", {}));
    await user.type(screen.getByLabelText(/model name/i), "support-llm");
    await user.type(screen.getByLabelText(/^version$/i), "v3");
    await user.type(screen.getByLabelText(/parent version/i), "v2");
    await user.click(screen.getByRole("button", { name: /register version/i }));
    await waitFor(() => expect(apiMock.registerModel).toHaveBeenCalledWith("support-llm", "v3", "v2"));
    expect(await screen.findByText("support-llm")).toBeInTheDocument();
  });

  it("omits the parent version when left blank", async () => {
    const user = userEvent.setup();
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    apiMock.registerModel.mockResolvedValue({});
    renderBuild();
    await screen.findByText(/no model versions registered yet/i);
    await user.type(screen.getByLabelText(/model name/i), "m");
    await user.type(screen.getByLabelText(/^version$/i), "v1");
    await user.click(screen.getByRole("button", { name: /register version/i }));
    await waitFor(() => expect(apiMock.registerModel).toHaveBeenCalledWith("m", "v1", undefined));
  });

  it("disables register until name and version are entered", async () => {
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    renderBuild();
    await screen.findByText(/no model versions registered yet/i);
    expect(screen.getByRole("button", { name: /register version/i })).toBeDisabled();
  });

  it("shows a generic error without server text when registration fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    apiMock.registerModel.mockRejectedValue(new ApiError(409, "Model version already registered", "internal detail"));
    renderBuild();
    await screen.findByText(/no model versions registered yet/i);
    await user.type(screen.getByLabelText(/model name/i), "m");
    await user.type(screen.getByLabelText(/^version$/i), "v1");
    await user.click(screen.getByRole("button", { name: /register version/i }));
    expect(await screen.findByText(/could not register the model version/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels the register form in Indonesian", async () => {
    apiMock.listModels.mockResolvedValue({ models: [], next_cursor: null });
    renderBuild("id");
    expect(await screen.findByRole("button", { name: /daftarkan versi/i })).toBeInTheDocument();
  });

  const RUN_ID = "3f2c8a52-1b7e-4c1d-9a55-0d2f6a9b7c11";
  const pendingModel = {
    name: "support-llm",
    version: "v3",
    parent_version: null,
    lineage: {},
    eval_scores: {},
    approval_status: "pending",
    approved_by: null,
  };

  it("attaches an eval run to a pending model version and reloads", async () => {
    const user = userEvent.setup();
    apiMock.listModels.mockResolvedValue({ models: [pendingModel], next_cursor: null });
    apiMock.attachEvalRun.mockResolvedValue({ ...pendingModel, eval_scores: { [RUN_ID]: {} } });
    renderBuild();
    await screen.findByText("support-llm");
    await user.type(screen.getByLabelText(/eval run id/i), RUN_ID);
    await user.click(screen.getByRole("button", { name: /attach eval run/i }));
    await waitFor(() => expect(apiMock.attachEvalRun).toHaveBeenCalledWith("support-llm", "v3", RUN_ID));
    await waitFor(() => expect(apiMock.listModels).toHaveBeenCalledTimes(2));
  });

  it("disables attach until a valid run id is entered", async () => {
    const user = userEvent.setup();
    apiMock.listModels.mockResolvedValue({ models: [pendingModel], next_cursor: null });
    renderBuild();
    await screen.findByText("support-llm");
    const button = screen.getByRole("button", { name: /attach eval run/i });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText(/eval run id/i), "not-a-uuid");
    expect(button).toBeDisabled();
  });

  it("shows a generic error without server text when attaching fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listModels.mockResolvedValue({ models: [pendingModel], next_cursor: null });
    apiMock.attachEvalRun.mockRejectedValue(new ApiError(404, "Eval run not found", "internal detail"));
    renderBuild();
    await screen.findByText("support-llm");
    await user.type(screen.getByLabelText(/eval run id/i), RUN_ID);
    await user.click(screen.getByRole("button", { name: /attach eval run/i }));
    expect(await screen.findByText(/could not attach the eval run/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("does not offer attach on decided versions and labels it in Indonesian", async () => {
    apiMock.listModels.mockResolvedValue({
      models: [{ ...pendingModel, approval_status: "approved" }, { ...pendingModel, version: "v4" }],
      next_cursor: null,
    });
    renderBuild("id");
    await screen.findAllByText("support-llm");
    expect(screen.getAllByRole("button", { name: /lampirkan hasil evaluasi/i })).toHaveLength(1);
  });
});
