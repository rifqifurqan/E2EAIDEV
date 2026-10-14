import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminScreen } from "./admin-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  deactivateUser: vi.fn(),
  getOrgSnapshot: vi.fn(),
  createDivision: vi.fn(),
  createTeam: vi.fn(),
  createOrgUser: vi.fn(),
  addTeamMember: vi.fn(),
  grantOrgRole: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

const TARGET = "3f2c8a52-1b7e-4c1d-9a55-0d2f6a9b7c11";
const MANAGER = "9a1d4e07-2c3b-4f6a-8b10-5e7d9c0a1f22";

const SNAPSHOT = {
  org_id: "11111111-1111-4111-8111-111111111111",
  divisions: [{ id: "d1", org_id: "o", name: "Finance" }],
  teams: [{ id: "t1", division_id: "d1", name: "Payroll Team" }],
  users: [
    { id: "u1", org_id: "o", email: "andi@demo.e2eai", display_name: "Andi", status: "active", division_id: "d1", manager_id: null },
    { id: "u2", org_id: "o", email: "budi@demo.e2eai", display_name: "Budi", status: "disabled", division_id: null, manager_id: null },
  ],
};

function renderAdmin(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <AdminScreen />
    </I18nProvider>,
  );
}

describe("AdminScreen", () => {
  beforeEach(() => {
    apiMock.deactivateUser.mockReset();
    apiMock.getOrgSnapshot.mockReset();
    apiMock.createDivision.mockReset();
    apiMock.createTeam.mockReset();
    apiMock.createOrgUser.mockReset();
    apiMock.addTeamMember.mockReset();
    apiMock.grantOrgRole.mockReset();
    apiMock.getOrgSnapshot.mockResolvedValue(SNAPSHOT);
  });

  it("renders offboarding section", () => {
    renderAdmin();
    expect(screen.getByText(/user offboarding/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deactivate user/i })).toBeInTheDocument();
  });

  it("renders runbook links", () => {
    renderAdmin();
    expect(screen.getByRole("link", { name: /service down/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /restore from backup/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /model endpoint failing/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /vector store degraded/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /permission sync lag/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /disk full/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /leaked key/i })).toBeInTheDocument();
  });

  it("renders configuration-as-code export link", () => {
    renderAdmin();
    const link = screen.getByRole("link", { name: /export configuration/i });
    expect(link).toHaveAttribute("href", "/api/v1/admin/config/export?format=yaml");
    expect(link).toHaveAttribute("download", "e2eai.yaml");
  });

  it("renders in Indonesian", () => {
    renderAdmin("id");
    expect(screen.getByText(/penonaktifan pengguna/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /nonaktifkan pengguna/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /layanan mati/i })).toBeInTheDocument();
  });

  it("deactivates a user and transfers their documents after an explicit confirm step", async () => {
    const user = userEvent.setup();
    apiMock.deactivateUser.mockResolvedValue({
      status: "disabled",
      documents_transferred: 3,
      folders_transferred: 1,
      sessions_purged: 2,
    });
    renderAdmin();
    expect(screen.queryByLabelText(/user to deactivate/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^deactivate user$/i }));
    const confirm = screen.getByRole("button", { name: /^confirm deactivation$/i });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/user to deactivate/i), ` ${TARGET} `);
    await user.type(screen.getByLabelText(/new owner/i), MANAGER);
    expect(apiMock.deactivateUser).not.toHaveBeenCalled();
    await user.click(confirm);
    await waitFor(() => expect(apiMock.deactivateUser).toHaveBeenCalledWith(TARGET, { transfer_to_id: MANAGER }));
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/user deactivated/i);
    expect(status).toHaveTextContent(/3 documents/i);
    expect(status).toHaveTextContent(/1 folders/i);
    expect(status).toHaveTextContent(/2 sessions/i);
  });

  it("keeps confirm disabled for non-UUID ids and when the user and new owner are the same", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(screen.getByRole("button", { name: /^deactivate user$/i }));
    const confirm = screen.getByRole("button", { name: /^confirm deactivation$/i });
    await user.type(screen.getByLabelText(/user to deactivate/i), "nope");
    await user.type(screen.getByLabelText(/new owner/i), MANAGER);
    expect(confirm).toBeDisabled();
    await user.clear(screen.getByLabelText(/user to deactivate/i));
    await user.type(screen.getByLabelText(/user to deactivate/i), MANAGER);
    expect(confirm).toBeDisabled();
    await user.clear(screen.getByLabelText(/user to deactivate/i));
    await user.type(screen.getByLabelText(/user to deactivate/i), TARGET);
    expect(confirm).toBeEnabled();
  });

  it("shows a generic error without server text when deactivation fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.deactivateUser.mockRejectedValue(new ApiError(400, "Cannot deactivate yourself", "stack detail"));
    renderAdmin();
    await user.click(screen.getByRole("button", { name: /^deactivate user$/i }));
    await user.type(screen.getByLabelText(/user to deactivate/i), TARGET);
    await user.type(screen.getByLabelText(/new owner/i), MANAGER);
    await user.click(screen.getByRole("button", { name: /^confirm deactivation$/i }));
    expect(await screen.findByText(/could not deactivate the user/i)).toBeInTheDocument();
    expect(screen.queryByText(/stack detail|yourself/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("labels the deactivation form in Indonesian", async () => {
    const user = userEvent.setup();
    renderAdmin("id");
    await user.click(screen.getByRole("button", { name: /^nonaktifkan pengguna$/i }));
    expect(screen.getByLabelText(/pengguna yang dinonaktifkan/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/pemilik baru/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^konfirmasi penonaktifan$/i })).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderAdmin();
    expect(screen.getByRole("heading", { name: /admin/i })).toBeInTheDocument();
  });

  it("lists divisions, teams and users from the org snapshot", async () => {
    renderAdmin();
    const org = await screen.findByRole("region", { name: /organization/i });
    expect(org).toHaveTextContent("Finance");
    expect(org).toHaveTextContent("Payroll Team");
    expect(org).toHaveTextContent("Andi");
    expect(org).toHaveTextContent("andi@demo.e2eai");
    expect(org).toHaveTextContent(/disabled/i);
    expect(apiMock.getOrgSnapshot).toHaveBeenCalledTimes(1);
  });

  it("shows an admin-only notice when the org snapshot is forbidden", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.getOrgSnapshot.mockRejectedValue(new ApiError(403, "Not allowed"));
    renderAdmin();
    expect(await screen.findByText(/organization view is available to admins only/i)).toBeInTheDocument();
    expect(screen.queryByText("Finance")).not.toBeInTheDocument();
  });

  it("shows a generic error without server text when the org snapshot fails", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.getOrgSnapshot.mockRejectedValue(new ApiError(500, "db exploded", "trace"));
    renderAdmin();
    expect(await screen.findByText(/could not load the organization/i)).toBeInTheDocument();
    expect(screen.queryByText(/db exploded|trace/i)).not.toBeInTheDocument();
  });

  it("renders the organization panel in Indonesian", async () => {
    renderAdmin("id");
    const org = await screen.findByRole("region", { name: /organisasi/i });
    expect(org).toHaveTextContent("Payroll Team");
  });

  it("creates a division in the admin's org and reloads the org panel", async () => {
    const user = userEvent.setup();
    apiMock.createDivision.mockResolvedValue({ id: "d2", org_id: SNAPSHOT.org_id, name: "Legal" });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    const add = screen.getByRole("button", { name: /^add division$/i });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText(/division name/i), "  Legal ");
    await user.click(add);
    await waitFor(() => expect(apiMock.createDivision).toHaveBeenCalledWith({ org_id: SNAPSHOT.org_id, name: "Legal" }));
    await waitFor(() => expect(apiMock.getOrgSnapshot).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText(/division name/i)).toHaveValue("");
  });

  it("creates a team under a chosen division", async () => {
    const user = userEvent.setup();
    apiMock.createTeam.mockResolvedValue({ id: "t2", division_id: "d1", name: "Audit" });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    const add = screen.getByRole("button", { name: /^add team$/i });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText(/team name/i), "Audit");
    await user.selectOptions(screen.getByLabelText(/^division$/i), "d1");
    await user.click(add);
    await waitFor(() => expect(apiMock.createTeam).toHaveBeenCalledWith({ division_id: "d1", name: "Audit" }));
    await waitFor(() => expect(apiMock.getOrgSnapshot).toHaveBeenCalledTimes(2));
  });

  it("shows a generic error without server text when creating a division fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.createDivision.mockRejectedValue(new ApiError(409, "duplicate secret detail"));
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    await user.type(screen.getByLabelText(/division name/i), "Legal");
    await user.click(screen.getByRole("button", { name: /^add division$/i }));
    expect(await screen.findByText(/could not create the division/i)).toBeInTheDocument();
    expect(screen.queryByText(/duplicate secret detail/i)).not.toBeInTheDocument();
  });

  it("labels the organization forms in Indonesian and hides them from non-admins", async () => {
    renderAdmin("id");
    await screen.findByRole("region", { name: /organisasi/i });
    expect(screen.getByRole("button", { name: /^tambah divisi$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^tambah tim$/i })).toBeInTheDocument();
  });

  it("does not render the create forms when the org view is forbidden", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiMock.getOrgSnapshot.mockRejectedValue(new ApiError(403, "no"));
    renderAdmin();
    await screen.findByText(/available to admins only/i);
    expect(screen.queryByRole("button", { name: /^add division$/i })).not.toBeInTheDocument();
  });

  it("creates a user in the admin's org with an optional division", async () => {
    const user = userEvent.setup();
    apiMock.createOrgUser.mockResolvedValue({ id: "u3" });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    const add = screen.getByRole("button", { name: /^add user$/i });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText(/^email$/i), "citra@demo.e2eai");
    await user.type(screen.getByLabelText(/display name/i), " Citra ");
    await user.selectOptions(screen.getByLabelText(/user division/i), "d1");
    await user.click(add);
    await waitFor(() =>
      expect(apiMock.createOrgUser).toHaveBeenCalledWith({
        org_id: SNAPSHOT.org_id,
        email: "citra@demo.e2eai",
        display_name: "Citra",
        division_id: "d1",
      }),
    );
    await waitFor(() => expect(apiMock.getOrgSnapshot).toHaveBeenCalledTimes(2));
  });

  it("keeps add user disabled for an invalid email and omits the division when none is chosen", async () => {
    const user = userEvent.setup();
    apiMock.createOrgUser.mockResolvedValue({ id: "u3" });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    const add = screen.getByRole("button", { name: /^add user$/i });
    await user.type(screen.getByLabelText(/display name/i), "Citra");
    await user.type(screen.getByLabelText(/^email$/i), "not-an-email");
    expect(add).toBeDisabled();
    await user.clear(screen.getByLabelText(/^email$/i));
    await user.type(screen.getByLabelText(/^email$/i), "citra@demo.e2eai");
    await user.click(add);
    await waitFor(() =>
      expect(apiMock.createOrgUser).toHaveBeenCalledWith({
        org_id: SNAPSHOT.org_id,
        email: "citra@demo.e2eai",
        display_name: "Citra",
      }),
    );
  });

  it("adds a user to a team chosen from the snapshot", async () => {
    const user = userEvent.setup();
    apiMock.addTeamMember.mockResolvedValue({ team_id: "t1", user_id: "u1" });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    const add = screen.getByRole("button", { name: /^add to team$/i });
    expect(add).toBeDisabled();
    await user.selectOptions(screen.getByLabelText(/member team/i), "t1");
    await user.selectOptions(screen.getByLabelText(/member user/i), "u1");
    await user.click(add);
    await waitFor(() => expect(apiMock.addTeamMember).toHaveBeenCalledWith({ team_id: "t1", user_id: "u1" }));
    expect(await screen.findByText(/member added/i)).toBeInTheDocument();
  });

  it("grants an org-wide role to a user from the fixed role list", async () => {
    const user = userEvent.setup();
    apiMock.grantOrgRole.mockResolvedValue({ user_id: "u1", role_name: "evaluator", project_id: null });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    const grant = screen.getByRole("button", { name: /^grant role$/i });
    expect(grant).toBeDisabled();
    await user.selectOptions(screen.getByLabelText(/role user/i), "u1");
    await user.selectOptions(screen.getByLabelText(/^role$/i), "evaluator");
    await user.click(grant);
    await waitFor(() => expect(apiMock.grantOrgRole).toHaveBeenCalledWith({ user_id: "u1", role_name: "evaluator" }));
    expect(await screen.findByText(/role granted/i)).toBeInTheDocument();
  });

  it("asks for an explicit confirmation before granting the admin role", async () => {
    const user = userEvent.setup();
    apiMock.grantOrgRole.mockResolvedValue({ user_id: "u1", role_name: "admin", project_id: null });
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    await user.selectOptions(screen.getByLabelText(/role user/i), "u1");
    await user.selectOptions(screen.getByLabelText(/^role$/i), "admin");
    const grant = screen.getByRole("button", { name: /^grant role$/i });
    expect(grant).toBeDisabled();
    await user.click(screen.getByLabelText(/i understand.*full administrator/i));
    expect(grant).toBeEnabled();
    await user.click(grant);
    await waitFor(() => expect(apiMock.grantOrgRole).toHaveBeenCalledWith({ user_id: "u1", role_name: "admin" }));
  });

  it("shows generic errors without server text for user, member and role failures", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    apiMock.createOrgUser.mockRejectedValue(new ApiError(409, "user already exists LEAK1"));
    apiMock.addTeamMember.mockRejectedValue(new ApiError(404, "team gone LEAK2"));
    apiMock.grantOrgRole.mockRejectedValue(new ApiError(403, "nope LEAK3"));
    renderAdmin();
    await screen.findByRole("region", { name: /organization/i });
    await user.type(screen.getByLabelText(/^email$/i), "citra@demo.e2eai");
    await user.type(screen.getByLabelText(/display name/i), "Citra");
    await user.click(screen.getByRole("button", { name: /^add user$/i }));
    expect(await screen.findByText(/could not create the user/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/member team/i), "t1");
    await user.selectOptions(screen.getByLabelText(/member user/i), "u1");
    await user.click(screen.getByRole("button", { name: /^add to team$/i }));
    expect(await screen.findByText(/could not add the member/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/role user/i), "u1");
    await user.selectOptions(screen.getByLabelText(/^role$/i), "evaluator");
    await user.click(screen.getByRole("button", { name: /^grant role$/i }));
    expect(await screen.findByText(/could not grant the role/i)).toBeInTheDocument();
    expect(screen.queryByText(/LEAK[123]/)).not.toBeInTheDocument();
  });

  it("labels the user, member and role forms in Indonesian", async () => {
    renderAdmin("id");
    await screen.findByRole("region", { name: /organisasi/i });
    expect(screen.getByRole("button", { name: /^tambah pengguna$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^tambah ke tim$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^berikan peran$/i })).toBeInTheDocument();
  });
});
