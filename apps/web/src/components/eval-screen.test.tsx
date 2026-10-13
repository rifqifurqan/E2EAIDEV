import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvalScreen } from "./eval-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listEvalRuns: vi.fn(),
  listEvalDatasets: vi.fn(),
  createDataset: vi.fn(),
  runEval: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderEval(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <EvalScreen />
    </I18nProvider>,
  );
}

function fireJson(el: HTMLElement, value: string) {
  // user.type treats "{" / "[" as special key syntax; set the value directly instead.
  fireEvent.change(el, { target: { value } });
}

describe("EvalScreen", () => {
  beforeEach(() => {
    apiMock.listEvalRuns.mockReset();
    apiMock.listEvalRuns.mockResolvedValue({ runs: [], next_cursor: null });
    apiMock.listEvalDatasets.mockReset();
    apiMock.listEvalDatasets.mockResolvedValue({ datasets: [], next_cursor: null });
    apiMock.createDataset.mockReset();
    apiMock.runEval.mockReset();
  });

  it("lists datasets with version, source and item count", async () => {
    apiMock.listEvalDatasets.mockResolvedValue({
      datasets: [
        { id: "d1", name: "permission-smoke", version: 2, source: "synthetic", item_count: 14, created_at: null },
      ],
      next_cursor: null,
    });
    renderEval();
    expect(await screen.findByText("permission-smoke")).toBeInTheDocument();
    expect(screen.getByText(/v2 · synthetic · 14/)).toBeInTheDocument();
  });

  it("shows the empty datasets state", async () => {
    renderEval();
    expect(await screen.findByText(/no datasets yet/i)).toBeInTheDocument();
  });

  it("shows an admin-only notice for datasets on 403", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listEvalDatasets.mockRejectedValue(new ApiError(403, "Forbidden"));
    renderEval();
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
  });

  it("lists eval runs with adapter, status and metrics", async () => {
    apiMock.listEvalRuns.mockResolvedValue({
      runs: [
        {
          id: "r1",
          dataset_id: "d1",
          adapter: "ragas.local",
          status: "completed",
          metrics: { answer_correctness: 0.9, items: 2 },
          created_at: "2026-10-14T00:00:00+00:00",
        },
      ],
      next_cursor: null,
    });
    renderEval();
    expect(await screen.findByText("ragas.local")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText(/answer_correctness: 0.9/)).toBeInTheDocument();
  });

  it("shows the empty runs state", async () => {
    renderEval();
    expect(await screen.findByText(/no evaluation runs yet/i)).toBeInTheDocument();
  });

  it("shows an admin-only notice on 403", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listEvalRuns.mockRejectedValue(new ApiError(403, "Forbidden"));
    renderEval();
    expect(await screen.findByRole("alert")).toHaveTextContent(/administrators only/i);
  });

  it("shows the runs empty state in Indonesian", async () => {
    renderEval("id");
    expect(await screen.findByText(/belum ada eksekusi evaluasi/i)).toBeInTheDocument();
  });

  it("renders datasets and runs sections", () => {
    renderEval();
    expect(screen.getByRole("heading", { name: /datasets/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /runs/i })).toBeInTheDocument();
  });

  it("renders permission leak summary", () => {
    renderEval();
    expect(screen.getByText(/permission leak summary/i)).toBeInTheDocument();
  });

  it("renders action buttons", () => {
    renderEval();
    expect(screen.getByRole("button", { name: /new dataset/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run evaluation/i })).toBeInTheDocument();
  });

  it("renders in Indonesian", () => {
    renderEval("id");
    expect(screen.getByRole("heading", { name: /dataset/i })).toBeInTheDocument();
    expect(screen.getByText(/ringkasan kebocoran izin/i)).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderEval();
    expect(screen.getByRole("heading", { name: /eval lab/i })).toBeInTheDocument();
  });
  it("shows the leak count from the latest permission-leak run", async () => {
    apiMock.listEvalRuns.mockResolvedValue({
      runs: [
        { id: "r2", dataset_id: "d1", adapter: "permission-leak.local", status: "completed", metrics: { leaks: 2, probes: 5, leak_rate: 0.4 }, created_at: "2026-10-14T00:00:00+00:00" },
        { id: "r1", dataset_id: "d1", adapter: "permission-leak.local", status: "completed", metrics: { leaks: 0, probes: 5, leak_rate: 0 }, created_at: "2026-10-13T00:00:00+00:00" },
      ],
      next_cursor: null,
    });
    renderEval();
    const summary = await screen.findByTestId("leak-summary-result");
    expect(summary).toHaveTextContent(/leak count: 2/i);
    expect(summary).toHaveTextContent(/5/);
    expect(screen.queryByText(/no leaks detected/i)).not.toBeInTheDocument();
  });

  it("shows no leaks only when the latest permission-leak run has zero leaks", async () => {
    apiMock.listEvalRuns.mockResolvedValue({
      runs: [
        { id: "r1", dataset_id: "d1", adapter: "permission-leak.local", status: "completed", metrics: { leaks: 0, probes: 3, leak_rate: 0 }, created_at: "2026-10-13T00:00:00+00:00" },
      ],
      next_cursor: null,
    });
    renderEval();
    expect(await screen.findByText(/no leaks detected/i)).toBeInTheDocument();
  });

  it("does not claim no leaks when no permission-leak run exists", async () => {
    renderEval();
    expect(await screen.findByText(/no permission-leak run yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/no leaks detected/i)).not.toBeInTheDocument();
  });

  it("shows the no-leak-run notice in Indonesian", async () => {
    renderEval("id");
    expect(await screen.findByText(/belum ada eksekusi uji kebocoran izin/i)).toBeInTheDocument();
  });
  it("creates a dataset from the form and refreshes the list", async () => {
    const user = userEvent.setup();
    apiMock.createDataset.mockResolvedValue({ id: "d9", name: "smoke", version: 1, items: 1 });
    renderEval();
    await screen.findByText(/no datasets yet/i);
    apiMock.listEvalDatasets.mockResolvedValue({
      datasets: [{ id: "d9", name: "smoke", version: 1, source: "manual", item_count: 1, created_at: null }],
      next_cursor: null,
    });
    await user.click(screen.getByRole("button", { name: /new dataset/i }));
    await user.type(screen.getByLabelText(/dataset name/i), "smoke");
    fireJson(screen.getByLabelText(/items \(json array\)/i), '[{"question":"q","expected_answer":"a","answer":"a"}]');
    await user.click(screen.getByRole("button", { name: /create dataset/i }));
    await waitFor(() =>
      expect(apiMock.createDataset).toHaveBeenCalledWith("smoke", "manual", [
        { question: "q", expected_answer: "a", answer: "a" },
      ]),
    );
    expect(await screen.findByText(/v1 · manual · 1/)).toBeInTheDocument();
  });

  it("rejects invalid dataset JSON without calling the API", async () => {
    const user = userEvent.setup();
    renderEval();
    await user.click(screen.getByRole("button", { name: /new dataset/i }));
    await user.type(screen.getByLabelText(/dataset name/i), "bad");
    fireJson(screen.getByLabelText(/items \(json array\)/i), "{not json");
    await user.click(screen.getByRole("button", { name: /create dataset/i }));
    expect(await screen.findByText(/items must be a json array/i)).toBeInTheDocument();
    expect(apiMock.createDataset).not.toHaveBeenCalled();
  });

  it("runs an evaluation on the selected dataset and refreshes runs", async () => {
    const user = userEvent.setup();
    apiMock.listEvalDatasets.mockResolvedValue({
      datasets: [{ id: "d1", name: "permission-smoke", version: 2, source: "synthetic", item_count: 14, created_at: null }],
      next_cursor: null,
    });
    apiMock.runEval.mockResolvedValue({ id: "r7", adapter: "ragas.local", metrics: {} });
    renderEval();
    await screen.findByText("permission-smoke");
    apiMock.listEvalRuns.mockResolvedValue({
      runs: [{ id: "r7", dataset_id: "d1", adapter: "ragas.local", status: "completed", metrics: { answer_correctness: 1 }, created_at: null }],
      next_cursor: null,
    });
    await user.click(screen.getByRole("button", { name: /run evaluation/i }));
    await waitFor(() => expect(apiMock.runEval).toHaveBeenCalledWith("d1", "ragas.local"));
    expect(await screen.findByText(/answer_correctness: 1/)).toBeInTheDocument();
  });

  it("disables run evaluation when there are no datasets", async () => {
    renderEval();
    await screen.findByText(/no datasets yet/i);
    expect(screen.getByRole("button", { name: /run evaluation/i })).toBeDisabled();
  });

  it("shows a generic error when running the evaluation fails", async () => {
    const user = userEvent.setup();
    apiMock.listEvalDatasets.mockResolvedValue({
      datasets: [{ id: "d1", name: "x", version: 1, source: "manual", item_count: 1, created_at: null }],
      next_cursor: null,
    });
    apiMock.runEval.mockRejectedValue(new Error("boom: internal stack"));
    renderEval();
    await screen.findByText("x");
    await user.click(screen.getByRole("button", { name: /run evaluation/i }));
    const alert = await screen.findByText(/could not run the evaluation/i);
    expect(alert).toBeInTheDocument();
    expect(screen.queryByText(/internal stack/i)).not.toBeInTheDocument();
  });

  it("labels the dataset form in Indonesian", async () => {
    const user = userEvent.setup();
    renderEval("id");
    await user.click(screen.getByRole("button", { name: /dataset baru/i }));
    expect(screen.getByLabelText(/nama dataset/i)).toBeInTheDocument();
  });
});
