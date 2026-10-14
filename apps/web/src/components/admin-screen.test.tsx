import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminScreen } from "./admin-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  deactivateUser: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: apiMock };
});

const TARGET = "3f2c8a52-1b7e-4c1d-9a55-0d2f6a9b7c11";
const MANAGER = "9a1d4e07-2c3b-4f6a-8b10-5e7d9c0a1f22";

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
});
