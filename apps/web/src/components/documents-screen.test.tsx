import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentsScreen } from "./documents-screen";
import { I18nProvider } from "@/i18n/context";

const apiMock = vi.hoisted(() => ({
  listDocuments: vi.fn(),
  searchDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  shareDocument: vi.fn(),
  trashDocument: vi.fn(),
  restoreDocument: vi.fn(),
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
    apiMock.listDocuments.mockReset();
    apiMock.listDocuments.mockResolvedValue({ documents: [], next_cursor: null });
    apiMock.searchDocuments.mockReset();
    apiMock.searchDocuments.mockResolvedValue({ results: [], next_cursor: null });
    apiMock.uploadDocument.mockReset();
    apiMock.shareDocument.mockReset();
    apiMock.trashDocument.mockReset();
    apiMock.restoreDocument.mockReset();
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

  it("renders share and trash buttons", () => {
    renderDocs();
    expect(screen.getByRole("button", { name: /share/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /move to trash/i })).toBeInTheDocument();
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

  it("loads persisted documents from the API on mount", async () => {
    apiMock.listDocuments.mockResolvedValueOnce({
      documents: [{ document_id: "doc1", title: "persisted-policy.txt", status: "active", sensitivity: "internal", parse_status: "parsed", scan_status: "clean" }],
      next_cursor: null,
    });
    renderDocs();
    expect(await screen.findByText(/persisted-policy\.txt/i)).toBeInTheDocument();
    expect(apiMock.listDocuments).toHaveBeenCalledWith("my_documents");
  });

  it("switches tabs by loading the matching backend document view", async () => {
    const user = userEvent.setup();
    renderDocs();
    await user.click(screen.getByRole("tab", { name: /shared with me/i }));
    await waitFor(() => expect(apiMock.listDocuments).toHaveBeenLastCalledWith("shared_with_me"));
    await user.click(screen.getByRole("tab", { name: /my team/i }));
    await waitFor(() => expect(apiMock.listDocuments).toHaveBeenLastCalledWith("my_team"));
  });

  it("searches documents through the backend within the selected view", async () => {
    const user = userEvent.setup();
    apiMock.searchDocuments.mockResolvedValueOnce({
      results: [{ document_id: "doc2", title: "search-hit.txt", status: "active", sensitivity: "internal", parse_status: "parsed", scan_status: "clean" }],
      next_cursor: null,
    });
    renderDocs();
    await user.type(screen.getByRole("searchbox"), "search-hit");
    await waitFor(() => expect(apiMock.searchDocuments).toHaveBeenCalledWith("search-hit", "my_documents"));
    expect(await screen.findByText(/search-hit\.txt/i)).toBeInTheDocument();
  });

  it("share and trash actions call document APIs when a document exists", async () => {
    apiMock.uploadDocument.mockResolvedValueOnce({ document_id: "doc1", title: "policy.pdf", status: "ready", sensitivity: "internal", parse_status: "parsed", scan_status: "clean" });
    apiMock.shareDocument.mockResolvedValueOnce({ status: "ok" });
    apiMock.trashDocument.mockResolvedValueOnce({ status: "trashed" });
    renderDocs();
    await userEvent.upload(screen.getByLabelText(/upload document/i), new File(["hello"], "policy.pdf", { type: "application/pdf" }));
    await userEvent.type(screen.getByLabelText(/share principal/i), "user:andi");
    await userEvent.click(screen.getByRole("button", { name: /^share$/i }));
    expect(apiMock.shareDocument).toHaveBeenCalledWith("doc1", { principal: "user:andi", level: "viewer" });
    await userEvent.click(screen.getByRole("button", { name: /move to trash/i }));
    expect(apiMock.trashDocument).toHaveBeenCalledWith("doc1");
  });

  it("tells a signed-out visitor to sign in instead of 'Could not load' (UAT-DOC-007)", async () => {
    const { ApiError } = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
    apiMock.listDocuments.mockReset();
    apiMock.listDocuments.mockRejectedValue(new ApiError(401, "Not authenticated"));
    renderDocs();
    expect(await screen.findByText(/please sign in to see your documents/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not load documents/i)).not.toBeInTheDocument();
  });

  it("trash tab lists trashed documents with Restore (UAT-DOC-006)", async () => {
    const user = userEvent.setup();
    apiMock.listDocuments.mockImplementation(async (view: string) =>
      view === "trash"
        ? { documents: [{ document_id: "d9", title: "old-policy.txt", status: "trashed", sensitivity: "internal", parse_status: "ready", scan_status: "clean" }], next_cursor: null }
        : { documents: [], next_cursor: null });
    apiMock.restoreDocument.mockResolvedValueOnce({ status: "active" });
    renderDocs();
    await user.click(screen.getByRole("tab", { name: /trash/i }));
    expect(await screen.findByText(/old-policy\.txt/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^restore$/i }));
    expect(apiMock.restoreDocument).toHaveBeenCalledWith("d9");
    await waitFor(() => expect(screen.queryByRole("button", { name: /old-policy\.txt/i })).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent(/restored/i);
  });

  it("localizes upload status messages in Indonesian (UAT-I18N-001)", async () => {
    const user = userEvent.setup();
    apiMock.uploadDocument.mockResolvedValueOnce({ document_id: "d1", title: "cuti.txt", status: "active", sensitivity: "internal", parse_status: "ready", scan_status: "clean" });
    renderDocs("id");
    await user.upload(screen.getByLabelText(/unggah dokumen/i), new File(["x"], "cuti.txt", { type: "text/plain" }));
    expect(await screen.findByText(/unggah selesai/i)).toBeInTheDocument();
    expect(screen.queryByText(/upload complete/i)).not.toBeInTheDocument();
  });

  it("shows the API's reason when sharing is rejected (UAT-DOC-005)", async () => {
    const user = userEvent.setup();
    const { ApiError } = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
    apiMock.uploadDocument.mockResolvedValueOnce({ document_id: "d1", title: "a.txt", status: "active", sensitivity: "internal", parse_status: "ready", scan_status: "clean" });
    apiMock.shareDocument.mockRejectedValueOnce(new ApiError(422, "Invalid principal", "Use user:<id>"));
    renderDocs();
    await user.upload(screen.getByLabelText(/upload document/i), new File(["x"], "a.txt", { type: "text/plain" }));
    await user.type(screen.getByLabelText(/share principal/i), "user:not-a-uuid");
    await user.click(screen.getByRole("button", { name: /^share$/i }));
    expect(await screen.findByText(/invalid principal/i)).toBeInTheDocument();
    expect(screen.queryByText(/^shared a\.txt/i)).not.toBeInTheDocument();
  });
  describe("parse status for async ingestion (FR-D3, FR-F20)", () => {
    const doc = (parse_status: string, title = "mitra.pdf") => ({
      document_id: "p1", title, status: "active", sensitivity: "internal", parse_status, scan_status: "clean",
    });

    it("shows a processing badge while a rich document is still being parsed", async () => {
      apiMock.listDocuments.mockResolvedValue({ documents: [doc("pending")], next_cursor: null });
      renderDocs();
      expect(await screen.findByText(/^processing/i)).toBeInTheDocument();
    });

    it("keeps showing 'processing' while the document is being indexed (parsed, not yet searchable)", async () => {
      apiMock.listDocuments.mockResolvedValue({ documents: [doc("indexing")], next_cursor: null });
      renderDocs();
      expect(await screen.findByText(/^processing/i)).toBeInTheDocument();
    });

    it("shows a failed badge in Indonesian when parsing failed", async () => {
      apiMock.listDocuments.mockResolvedValue({ documents: [doc("failed")], next_cursor: null });
      renderDocs("id");
      expect(await screen.findByText(/gagal diproses/i)).toBeInTheDocument();
    });

    it("shows no badge for a ready document", async () => {
      apiMock.listDocuments.mockResolvedValue({ documents: [doc("ready")], next_cursor: null });
      renderDocs();
      await screen.findByText(/mitra\.pdf/i);
      expect(screen.queryByText(/^processing/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/could not be processed/i)).not.toBeInTheDocument();
    });

    it("tells the user an uploaded PDF is being processed", async () => {
      const user = userEvent.setup();
      apiMock.uploadDocument.mockResolvedValueOnce(doc("pending"));
      renderDocs();
      await user.upload(screen.getByLabelText(/upload document/i), new File(["%PDF"], "mitra.pdf", { type: "application/pdf" }));
      expect(await screen.findByText(/upload received.*processing/i)).toBeInTheDocument();
    });

    it("refreshes the list until the document is ready, then stops polling", async () => {
      apiMock.listDocuments
        .mockResolvedValueOnce({ documents: [doc("pending")], next_cursor: null })
        .mockResolvedValueOnce({ documents: [doc("pending")], next_cursor: null })
        .mockResolvedValue({ documents: [doc("ready")], next_cursor: null });
      renderDocs();
      expect(await screen.findByText(/^processing/i)).toBeInTheDocument();
      await waitFor(() => expect(screen.queryByText(/^processing/i)).not.toBeInTheDocument(), { timeout: 12000 });
      const calls = apiMock.listDocuments.mock.calls.length;
      expect(calls).toBeGreaterThanOrEqual(3);
      await new Promise((resolve) => setTimeout(resolve, 3500));
      expect(apiMock.listDocuments.mock.calls.length).toBe(calls); // nothing pending: no more polling
    }, 20000);
  });
});
