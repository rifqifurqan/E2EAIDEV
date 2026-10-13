import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentsScreen } from "./documents-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  uploadDocument: vi.fn(),
  shareDocument: vi.fn(),
  trashDocument: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: apiMock,
}));

function renderDocs(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <DocumentsScreen />
    </I18nProvider>,
  );
}

describe("DocumentsScreen", () => {
  beforeEach(() => {
    apiMock.uploadDocument.mockReset();
    apiMock.shareDocument.mockReset();
    apiMock.trashDocument.mockReset();
  });

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

  it("exposes a real file input and uploads the selected file", async () => {
    apiMock.uploadDocument.mockResolvedValueOnce({ document_id: "doc1", title: "policy.pdf", status: "ready", sensitivity: "internal", parse_status: "parsed", scan_status: "clean" });
    renderDocs();
    const file = new File(["hello"], "policy.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText(/upload document/i), file);
    expect(apiMock.uploadDocument).toHaveBeenCalledWith(file);
    expect(await screen.findByText(/policy\.pdf/i)).toBeInTheDocument();
  });

  it("share and revoke actions call document APIs when a document exists", async () => {
    apiMock.uploadDocument.mockResolvedValueOnce({ document_id: "doc1", title: "policy.pdf", status: "ready", sensitivity: "internal", parse_status: "parsed", scan_status: "clean" });
    apiMock.shareDocument.mockResolvedValueOnce({ status: "ok" });
    apiMock.trashDocument.mockResolvedValueOnce({ status: "trashed" });
    renderDocs();
    await userEvent.upload(screen.getByLabelText(/upload document/i), new File(["hello"], "policy.pdf", { type: "application/pdf" }));
    await userEvent.type(screen.getByLabelText(/share principal/i), "user:andi");
    await userEvent.click(screen.getByRole("button", { name: /^share$/i }));
    expect(apiMock.shareDocument).toHaveBeenCalledWith("doc1", { principal: "user:andi", level: "viewer" });
    await userEvent.click(screen.getByRole("button", { name: /revoke/i }));
    expect(apiMock.trashDocument).toHaveBeenCalledWith("doc1");
  });
});
