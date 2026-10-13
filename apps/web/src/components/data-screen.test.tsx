import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataScreen } from "./data-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listDueReviews: vi.fn(),
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
});
