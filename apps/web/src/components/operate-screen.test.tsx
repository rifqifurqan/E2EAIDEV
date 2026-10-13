import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OperateScreen } from "./operate-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listIncidents: vi.fn(),
  listIncidentsPage: vi.fn(),
  transitionIncident: vi.fn(),
  recordPostmortem: vi.fn(),
  reportIncident: vi.fn(),
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
    apiMock.listIncidentsPage.mockReset();
    apiMock.transitionIncident.mockReset();
    apiMock.recordPostmortem.mockReset();
    apiMock.reportIncident.mockReset();
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
    const row = screen.getByText("Wrong salary answer").closest("li") as HTMLElement;
    expect(within(row).getByText(/sev2/i)).toBeInTheDocument();
    expect(within(row).getByText(/^triaged$/i)).toBeInTheDocument();
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
  const released = (postmortem: Record<string, unknown> | null) => ({
    incidents: [{ id: "x1", title: "Wrong salary answer", severity: "sev2", status: "released", postmortem }],
    next_cursor: null,
  });

  it("records a post-incident record for a released incident without one", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue(released(null));
    apiMock.recordPostmortem.mockResolvedValue({});
    renderOperate();
    await screen.findByText("Wrong salary answer");
    const submit = screen.getByRole("button", { name: /record post-incident/i });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/^summary/i), "Wrong answer shipped");
    await user.type(screen.getByLabelText(/root cause/i), "Stale policy index");
    apiMock.listIncidents.mockResolvedValue(released({ summary: "Wrong answer shipped" }));
    await user.click(submit);
    await waitFor(() =>
      expect(apiMock.recordPostmortem).toHaveBeenCalledWith("x1", {
        summary: "Wrong answer shipped",
        root_cause: "Stale policy index",
      }),
    );
    expect(await screen.findByRole("button", { name: /move to closed/i })).toBeInTheDocument();
  });

  it("closes a released incident once the post-incident record exists", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue(released({ summary: "s", root_cause: "r" }));
    apiMock.transitionIncident.mockResolvedValue({});
    renderOperate();
    await screen.findByText("Wrong salary answer");
    expect(screen.queryByRole("button", { name: /record post-incident/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /move to closed/i }));
    await waitFor(() => expect(apiMock.transitionIncident).toHaveBeenCalledWith("x1", { to_status: "closed" }));
  });

  it("shows no lifecycle controls for a closed incident", async () => {
    apiMock.listIncidents.mockResolvedValue({
      incidents: [{ id: "x1", title: "Wrong salary answer", severity: "sev2", status: "closed", postmortem: { summary: "s" } }],
      next_cursor: null,
    });
    renderOperate();
    await screen.findByText("Wrong salary answer");
    expect(screen.queryByRole("button", { name: /move to|record post-incident/i })).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when the post-incident record fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listIncidents.mockResolvedValue(released(null));
    apiMock.recordPostmortem.mockRejectedValue(new ApiError(409, "Post-incident record needs a fixed incident", "internal detail"));
    renderOperate();
    await screen.findByText("Wrong salary answer");
    await user.type(screen.getByLabelText(/^summary/i), "s");
    await user.type(screen.getByLabelText(/root cause/i), "r");
    await user.click(screen.getByRole("button", { name: /record post-incident/i }));
    expect(await screen.findByText(/could not save the post-incident record/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels the post-incident form in Indonesian", async () => {
    apiMock.listIncidents.mockResolvedValue(released(null));
    renderOperate("id");
    expect(await screen.findByRole("button", { name: /catat pasca-insiden/i })).toBeInTheDocument();
  });
  it("reports a new incident with a severity and reloads the list", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue({ incidents: [], next_cursor: null });
    apiMock.reportIncident.mockResolvedValue({});
    renderOperate();
    await screen.findByText(/no open ai incidents/i);
    apiMock.listIncidents.mockResolvedValue(list("reported"));
    await user.type(screen.getByLabelText(/incident title/i), "Wrong salary answer");
    await user.selectOptions(screen.getByLabelText(/severity/i), "sev2");
    await user.type(screen.getByLabelText(/^description/i), "Bot quoted last year's table");
    await user.click(screen.getByRole("button", { name: /report incident/i }));
    await waitFor(() =>
      expect(apiMock.reportIncident).toHaveBeenCalledWith({
        title: "Wrong salary answer",
        severity: "sev2",
        description: "Bot quoted last year's table",
      }),
    );
    expect(await screen.findByText("Wrong salary answer")).toBeInTheDocument();
  });

  it("disables report until a title is entered and defaults to sev3", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue({ incidents: [], next_cursor: null });
    apiMock.reportIncident.mockResolvedValue({});
    renderOperate();
    await screen.findByText(/no open ai incidents/i);
    const submit = screen.getByRole("button", { name: /report incident/i });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/incident title/i), "Leak?");
    await user.click(submit);
    await waitFor(() =>
      expect(apiMock.reportIncident).toHaveBeenCalledWith({ title: "Leak?", severity: "sev3" }),
    );
  });

  it("still offers the report form to non-admins when the list is forbidden", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listIncidents.mockRejectedValue(new ApiError(403, "Forbidden"));
    renderOperate();
    expect(await screen.findByRole("button", { name: /report incident/i })).toBeInTheDocument();
  });

  it("shows a generic error without server text when reporting fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listIncidents.mockResolvedValue({ incidents: [], next_cursor: null });
    apiMock.reportIncident.mockRejectedValue(new ApiError(400, "Severity must be one of", "internal detail"));
    renderOperate();
    await screen.findByText(/no open ai incidents/i);
    await user.type(screen.getByLabelText(/incident title/i), "x");
    await user.click(screen.getByRole("button", { name: /report incident/i }));
    expect(await screen.findByText(/could not report the incident/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/i)).not.toBeInTheDocument();
  });

  it("labels the report form in Indonesian", async () => {
    apiMock.listIncidents.mockResolvedValue({ incidents: [], next_cursor: null });
    renderOperate("id");
    expect(await screen.findByRole("button", { name: /laporkan insiden/i })).toBeInTheDocument();
  });

  it("loads more incidents with the next cursor and hides the button at the end", async () => {
    const user = userEvent.setup();
    apiMock.listIncidents.mockResolvedValue({
      incidents: [{ id: "p1", title: "First page incident", severity: "sev3", status: "reported" }],
      next_cursor: "cur-2",
    });
    apiMock.listIncidentsPage.mockResolvedValue({
      incidents: [{ id: "p2", title: "Second page incident", severity: "sev4", status: "reported" }],
      next_cursor: null,
    });
    renderOperate();
    await screen.findByText("First page incident");
    await user.click(screen.getByRole("button", { name: /load more/i }));
    expect(await screen.findByText("Second page incident")).toBeInTheDocument();
    expect(apiMock.listIncidentsPage).toHaveBeenCalledWith("cur-2");
    expect(screen.getByText("First page incident")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("shows no load-more button when there is no next cursor", async () => {
    apiMock.listIncidents.mockResolvedValue({
      incidents: [{ id: "p1", title: "Only incident", severity: "sev3", status: "reported" }],
      next_cursor: null,
    });
    renderOperate();
    await screen.findByText("Only incident");
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when loading more fails, keeping loaded rows", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.listIncidents.mockResolvedValue({
      incidents: [{ id: "p1", title: "First page incident", severity: "sev3", status: "reported" }],
      next_cursor: "cur-2",
    });
    apiMock.listIncidentsPage.mockRejectedValue(new ApiError(500, "boom", "stack detail"));
    renderOperate();
    await screen.findByText("First page incident");
    await user.click(screen.getByRole("button", { name: /load more/i }));
    expect(await screen.findByText(/could not load more/i)).toBeInTheDocument();
    expect(screen.queryByText(/stack detail/i)).not.toBeInTheDocument();
    expect(screen.getByText("First page incident")).toBeInTheDocument();
  });

  it("labels load more in Indonesian", async () => {
    apiMock.listIncidents.mockResolvedValue({
      incidents: [{ id: "p1", title: "Insiden", severity: "sev3", status: "reported" }],
      next_cursor: "cur-2",
    });
    renderOperate("id");
    expect(await screen.findByRole("button", { name: /muat lebih banyak/i })).toBeInTheDocument();
  });
});
