import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OperateScreen } from "./operate-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listIncidents: vi.fn(),
  transitionIncident: vi.fn(),
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
    apiMock.transitionIncident.mockReset();
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
  const list = (status: string) => ({
    incidents: [{ id: "x1", title: "Wrong salary answer", severity: "sev2", status }],
    next_cursor: null,
  });

  it("moves a reported incident to triaged and reloads", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue(list("reported"));
    apiMock.transitionIncident.mockResolvedValue({});
    renderOperate();
    await screen.findByText("Wrong salary answer");
    apiMock.listIncidents.mockResolvedValue(list("triaged"));
    await user.click(screen.getByRole("button", { name: /move to triaged/i }));
    await waitFor(() => expect(apiMock.transitionIncident).toHaveBeenCalledWith("x1", { to_status: "triaged" }));
    expect(await screen.findByRole("button", { name: /move to fixing/i })).toBeInTheDocument();
  });

  it("requires fix notes before moving a fixing incident to fixed", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue(list("fixing"));
    apiMock.transitionIncident.mockResolvedValue({});
    renderOperate();
    await screen.findByText("Wrong salary answer");
    expect(screen.getByRole("button", { name: /move to fixed/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/fix notes/i), "Corrected the HR policy index");
    await user.click(screen.getByRole("button", { name: /move to fixed/i }));
    await waitFor(() =>
      expect(apiMock.transitionIncident).toHaveBeenCalledWith("x1", {
        to_status: "fixed",
        fix_notes: "Corrected the HR policy index",
      }),
    );
  });

  it("requires a release reference before moving a fixed incident to released", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue(list("fixed"));
    apiMock.transitionIncident.mockResolvedValue({});
    renderOperate();
    await screen.findByText("Wrong salary answer");
    expect(screen.getByRole("button", { name: /move to released/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/release reference/i), "bundle-v7");
    await user.click(screen.getByRole("button", { name: /move to released/i }));
    await waitFor(() =>
      expect(apiMock.transitionIncident).toHaveBeenCalledWith("x1", { to_status: "released", release_ref: "bundle-v7" }),
    );
  });

  it("offers no transition button once released or closed", async () => {
    apiMock.listIncidents.mockResolvedValue(list("released"));
    renderOperate();
    await screen.findByText("Wrong salary answer");
    expect(screen.queryByRole("button", { name: /move to/i })).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when the transition fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listIncidents.mockResolvedValue(list("reported"));
    apiMock.transitionIncident.mockRejectedValue(new ApiError(409, "Cannot move", "internal detail"));
    renderOperate();
    await screen.findByText("Wrong salary answer");
    await user.click(screen.getByRole("button", { name: /move to triaged/i }));
    expect(await screen.findByText(/could not update the incident/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels the transition button in Indonesian", async () => {
    apiMock.listIncidents.mockResolvedValue(list("reported"));
    renderOperate("id");
    expect(await screen.findByRole("button", { name: /pindah ke triaged/i })).toBeInTheDocument();
  });
});
