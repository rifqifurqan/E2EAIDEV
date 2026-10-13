import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ImproveScreen } from "./improve-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listFlywheel: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderImprove(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <ImproveScreen />
    </I18nProvider>,
  );
}

describe("ImproveScreen", () => {
  beforeEach(() => {
    apiMock.listFlywheel.mockReset();
  });

  it("shows status counts and queue items from the live flywheel API", async () => {
    apiMock.listFlywheel.mockResolvedValue({
      by_status: { new: 2, accepted: 1 },
      by_source: { thumbs_down: 3 },
      items: [
        { id: "i1", source: "thumbs_down", status: "new", question: "How many leave days?", correction: null, reason: null, target: null },
      ],
      next_cursor: null,
    });
    renderImprove();
    expect(await screen.findByText("How many leave days?")).toBeInTheDocument();
    expect(screen.getByText(/new: 2/i)).toBeInTheDocument();
    expect(screen.getByText(/accepted: 1/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /feedback flywheel/i })).toBeInTheDocument();
  });

  it("shows an empty state when the queue has no items", async () => {
    apiMock.listFlywheel.mockResolvedValue({ by_status: {}, by_source: {}, items: [], next_cursor: null });
    renderImprove();
    expect(await screen.findByText(/no feedback items yet/i)).toBeInTheDocument();
  });

  it("shows an admin-only notice on 403 instead of crashing", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listFlywheel.mockRejectedValue(new ApiError(403, "Forbidden"));
    renderImprove();
    expect(await screen.findByRole("alert")).toHaveTextContent(/administrator/i);
  });

  it("renders in Indonesian", async () => {
    apiMock.listFlywheel.mockResolvedValue({ by_status: {}, by_source: {}, items: [], next_cursor: null });
    renderImprove("id");
    expect(await screen.findByText(/belum ada item umpan balik/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: /flywheel umpan balik/i })).toBeInTheDocument());
  });
});
