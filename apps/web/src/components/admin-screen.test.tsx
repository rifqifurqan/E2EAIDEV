import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdminScreen } from "./admin-screen";
import { I18nProvider } from "@/i18n/context";

function renderAdmin(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <AdminScreen />
    </I18nProvider>,
  );
}

describe("AdminScreen", () => {
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

  it("renders in Indonesian", () => {
    renderAdmin("id");
    expect(screen.getByText(/penonaktifan pengguna/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /nonaktifkan pengguna/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /layanan mati/i })).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderAdmin();
    expect(screen.getByRole("heading", { name: /admin/i })).toBeInTheDocument();
  });
});
