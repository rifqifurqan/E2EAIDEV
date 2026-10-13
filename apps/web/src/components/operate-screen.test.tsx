import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { OperateScreen } from "./operate-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listIncidents: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

function renderOperate(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <OperateScreen />
    </I18nProvider>,
  );
}

describe("OperateScreen", () => {
  beforeEach(() => {
    apiMock.listIncidents.mockReset();
  });

  it("lists AI incidents with severity and status next to the admin tools", async () => {
    apiMock.listIncidents.mockResolvedValue({
      incidents: [
        { id: "x1", title: "Wrong salary answer", severity: "sev2", status: "triaged" },
      ],
      next_cursor: null,
    });
    renderOperate();
    expect(await screen.findByText("Wrong salary answer")).toBeInTheDocument();
    expect(screen.getByText(/sev2/i)).toBeInTheDocument();
    expect(screen.getByText(/triaged/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /export configuration/i })).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    apiMock.listIncidents.mockResolvedValue({ incidents: [], next_cursor: null });
    renderOperate();
    expect(await screen.findByText(/no open ai incidents/i)).toBeInTheDocument();
  });

  it("shows an admin-only notice on 403", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listIncidents.mockRejectedValue(new ApiError(403, "Forbidden"));
    renderOperate();
    expect(await screen.findByRole("alert")).toHaveTextContent(/administrator/i);
  });

  it("renders in Indonesian", async () => {
    apiMock.listIncidents.mockResolvedValue({ incidents: [], next_cursor: null });
    renderOperate("id");
    expect(await screen.findByText(/tidak ada insiden ai terbuka/i)).toBeInTheDocument();
  });
});
