import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ImproveScreen } from "./improve-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listFlywheel: vi.fn(),
  triageFlywheelItem: vi.fn(),
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
    apiMock.triageFlywheelItem.mockReset();
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
  const queue = (status: string, correction: string | null) => ({
    by_status: { [status]: 1 },
    by_source: {},
    items: [{ id: "i1", source: "thumbs_down", status, question: "How many leave days?", correction, reason: null, target: null }],
    next_cursor: null,
  });

  it("accepts a queued item with a correction into the eval set and reloads", async () => {
    const user = userEvent.setup();
    apiMock.listFlywheel.mockResolvedValue(queue("queued", "12 days"));
    apiMock.triageFlywheelItem.mockResolvedValue({});
    renderImprove();
    await screen.findByText("How many leave days?");
    apiMock.listFlywheel.mockResolvedValue(queue("accepted", "12 days"));
    await user.click(screen.getByRole("button", { name: /accept for eval/i }));
    await waitFor(() => expect(apiMock.triageFlywheelItem).toHaveBeenCalledWith("i1", "accept", "eval"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /accept for eval/i })).not.toBeInTheDocument());
  });

  it("accepts a queued item into the fine-tune set", async () => {
    const user = userEvent.setup();
    apiMock.listFlywheel.mockResolvedValue(queue("queued", "12 days"));
    apiMock.triageFlywheelItem.mockResolvedValue({});
    renderImprove();
    await screen.findByText("How many leave days?");
    await user.click(screen.getByRole("button", { name: /accept for fine-tuning/i }));
    await waitFor(() => expect(apiMock.triageFlywheelItem).toHaveBeenCalledWith("i1", "accept", "finetune"));
  });

  it("disables accept when the item has no correction, but still allows dismiss", async () => {
    const user = userEvent.setup();
    apiMock.listFlywheel.mockResolvedValue(queue("queued", null));
    apiMock.triageFlywheelItem.mockResolvedValue({});
    renderImprove();
    await screen.findByText("How many leave days?");
    expect(screen.getByRole("button", { name: /accept for eval/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /accept for fine-tuning/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /dismiss/i }));
    await waitFor(() => expect(apiMock.triageFlywheelItem).toHaveBeenCalledWith("i1", "dismiss", undefined));
  });

  it("offers no triage buttons once an item is triaged", async () => {
    apiMock.listFlywheel.mockResolvedValue(queue("accepted", "12 days"));
    renderImprove();
    await screen.findByText("How many leave days?");
    expect(screen.queryByRole("button", { name: /dismiss/i })).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when triage fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listFlywheel.mockResolvedValue(queue("queued", "12 days"));
    apiMock.triageFlywheelItem.mockRejectedValue(new ApiError(409, "Item was already triaged", "internal detail"));
    renderImprove();
    await screen.findByText("How many leave days?");
    await user.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(await screen.findByText(/could not triage the item/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels triage buttons in Indonesian", async () => {
    apiMock.listFlywheel.mockResolvedValue(queue("queued", "12 hari"));
    renderImprove("id");
    expect(await screen.findByRole("button", { name: /terima untuk evaluasi/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /abaikan/i })).toBeInTheDocument();
  });
});
