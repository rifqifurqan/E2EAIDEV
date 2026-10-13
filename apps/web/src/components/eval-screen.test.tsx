import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvalScreen } from "./eval-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listEvalRuns: vi.fn(),
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

describe("EvalScreen", () => {
  beforeEach(() => {
    apiMock.listEvalRuns.mockReset();
    apiMock.listEvalRuns.mockResolvedValue({ runs: [], next_cursor: null });
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
});
