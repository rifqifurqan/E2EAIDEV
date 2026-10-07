import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DocumentsScreen } from "./documents-screen";
import { I18nProvider } from "@/i18n/context";

function renderDocs(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <DocumentsScreen />
    </I18nProvider>,
  );
}

describe("DocumentsScreen", () => {
  it("renders document view tabs", () => {
    renderDocs();
    expect(screen.getByRole("tab", { name: /my documents/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /shared with me/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /my team/i })).toBeInTheDocument();
  });

  it("renders upload button", () => {
    renderDocs();
    expect(screen.getByRole("button", { name: /upload/i })).toBeInTheDocument();
  });

  it("renders search input", () => {
    renderDocs();
    expect(screen.getByRole("searchbox")).toBeInTheDocument();
  });

  it("renders share and revoke buttons", () => {
    renderDocs();
    expect(screen.getByRole("button", { name: /share/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /revoke/i })).toBeInTheDocument();
  });

  it("renders in Indonesian", () => {
    renderDocs("id");
    expect(screen.getByRole("tab", { name: /dokumen saya/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /dibagikan kepada saya/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /unggah/i })).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderDocs();
    expect(screen.getByRole("heading", { name: /documents/i })).toBeInTheDocument();
  });
});
