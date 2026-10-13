import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BuildScreen } from "./build-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listModels: vi.fn(),
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
});
