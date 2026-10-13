import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataScreen } from "./data-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listDueReviews: vi.fn(),
  listDueReviewsPage: vi.fn(),
  markReviewed: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderData(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <DataScreen />
    </I18nProvider>,
  );
}

describe("DataScreen", () => {
  beforeEach(() => {
    apiMock.listDueReviews.mockReset();
    apiMock.listDueReviewsPage.mockReset();
    apiMock.markReviewed.mockReset();
  });

  it("lists documents whose review is due with overdue days", async () => {
    apiMock.listDueReviews.mockResolvedValue({
      reviews: [
        {
          document_id: "d1",
          title: "Leave policy 2025",
          review_at: "2026-09-01T00:00:00+00:00",
          overdue_days: 43,
          expires_at: null,
        },
      ],
      next_cursor: null,
    });
    renderData();
    expect(await screen.findByText("Leave policy 2025")).toBeInTheDocument();
    expect(screen.getByText(/43/)).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    apiMock.listDueReviews.mockResolvedValue({ reviews: [], next_cursor: null });
    renderData();
    expect(await screen.findByText(/no documents are due for review/i)).toBeInTheDocument();
  });

  it("shows a sign-in notice on 401", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listDueReviews.mockRejectedValue(new ApiError(401, "Unauthorized"));
    renderData();
    expect(await screen.findByRole("alert")).toHaveTextContent(/sign in/i);
  });

  it("shows a generic error without server text", async () => {
    apiMock.listDueReviews.mockRejectedValue(new Error("db password leaked"));
    renderData();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not load/i);
    expect(alert).not.toHaveTextContent(/leaked/);
  });

  it("renders in Indonesian", async () => {
    apiMock.listDueReviews.mockResolvedValue({ reviews: [], next_cursor: null });
    renderData("id");
    expect(await screen.findByText(/tidak ada dokumen yang jatuh tempo/i)).toBeInTheDocument();
  });
  const due = (id: string) => ({
    reviews: [{ document_id: id, title: "Leave policy", review_at: "2026-09-01T00:00:00+00:00", overdue_days: 13, expires_at: null }],
    next_cursor: null,
  });

  it("marks a document reviewed and removes it from the due list", async () => {
    const user = userEvent.setup();
    apiMock.listDueReviews.mockResolvedValue(due("d1"));
    apiMock.markReviewed.mockResolvedValue({ status: "ok", review_at: "2027-04-12T00:00:00+00:00" });
    renderData();
    await screen.findByText("Leave policy");
    apiMock.listDueReviews.mockResolvedValue({ reviews: [], next_cursor: null });
    await user.click(screen.getByRole("button", { name: /mark reviewed/i }));
    await waitFor(() => expect(apiMock.markReviewed).toHaveBeenCalledWith("d1", 180));
    expect(await screen.findByText(/no documents are due for review/i)).toBeInTheDocument();
  });

  it("uses the chosen next-review interval", async () => {
    const user = userEvent.setup();
    apiMock.listDueReviews.mockResolvedValue(due("d1"));
    apiMock.markReviewed.mockResolvedValue({ status: "ok", review_at: "x" });
    renderData();
    await screen.findByText("Leave policy");
    await user.selectOptions(screen.getByLabelText(/next review in/i), "90");
    await user.click(screen.getByRole("button", { name: /mark reviewed/i }));
    await waitFor(() => expect(apiMock.markReviewed).toHaveBeenCalledWith("d1", 90));
  });

  it("shows a generic error without server text when marking fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listDueReviews.mockResolvedValue(due("d1"));
    apiMock.markReviewed.mockRejectedValue(new ApiError(403, "Not allowed", "internal detail"));
    renderData();
    await screen.findByText("Leave policy");
    await user.click(screen.getByRole("button", { name: /mark reviewed/i }));
    expect(await screen.findByText(/could not mark the document as reviewed/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels the review action in Indonesian", async () => {
    apiMock.listDueReviews.mockResolvedValue(due("d1"));
    renderData("id");
    expect(await screen.findByRole("button", { name: /tandai sudah ditinjau/i })).toBeInTheDocument();
  });

  it("loads more due reviews with the next cursor", async () => {
    const user = userEvent.setup();
    const row = (id: string, title: string) => ({ document_id: id, title, review_at: "2026-09-01T00:00:00+00:00", overdue_days: 1, expires_at: null });
    apiMock.listDueReviews.mockResolvedValue({ reviews: [row("d1", "Doc page one")], next_cursor: "cur-2" });
    apiMock.listDueReviewsPage.mockResolvedValue({ reviews: [row("d2", "Doc page two")], next_cursor: null });
    renderData();
    await screen.findByText("Doc page one");
    await user.click(screen.getByRole("button", { name: /load more/i }));
    expect(await screen.findByText("Doc page two")).toBeInTheDocument();
    expect(apiMock.listDueReviewsPage).toHaveBeenCalledWith("cur-2");
    expect(screen.getByText("Doc page one")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });
});
