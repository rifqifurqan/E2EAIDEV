"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type Document } from "@/lib/api-client";

type DocView = "my" | "shared" | "team" | "trash";
type ApiDocView = "my_documents" | "shared_with_me" | "my_team" | "trash";

const VIEW_TO_API: Record<DocView, ApiDocView> = {
  my: "my_documents",
  shared: "shared_with_me",
  team: "my_team",
  trash: "trash",
};

/** Error title from the API's problem+json (never the stack/detail), else the fallback. */
function reason(error: unknown, fallback: string): string {
  const title = (error as { title?: unknown } | null)?.title;
  return typeof title === "string" && title ? title : fallback;
}

export function DocumentsScreen() {
  const { t } = useI18n();
  const [activeView, setActiveView] = useState<DocView>("my");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [sharePrincipal, setSharePrincipal] = useState("");
  const [status, setStatus] = useState("");
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef(0);

  const tabs: { key: DocView; label: string }[] = [
    { key: "my", label: t.documents.myDocuments },
    { key: "shared", label: t.documents.sharedWithMe },
    { key: "team", label: t.documents.myTeam },
    { key: "trash", label: t.documents.trash },
  ];

  const inTrash = activeView === "trash";
  const selectedDocument = documents.find((doc) => doc.document_id === selectedId) ?? documents[0];

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    const timer = window.setTimeout(() => {
      const view = VIEW_TO_API[activeView];
      const trimmed = query.trim();
      setLoading(true);
      setLoadError("");
      // The trash list is not searchable (search only covers active documents).
      const task = trimmed === "" || view === "trash" ? api.listDocuments(view) : api.searchDocuments(trimmed, view);
      task
        .then((result) => {
          if (requestId !== requestIdRef.current) return;
          const nextDocs = "documents" in result ? result.documents : result.results;
          setDocuments(nextDocs);
          setSelectedId((current) => (nextDocs.some((doc) => doc.document_id === current) ? current : ""));
        })
        .catch((error: unknown) => {
          if (requestId !== requestIdRef.current) return;
          setDocuments([]);
          setSelectedId("");
          // A signed-out visitor is not an error worth alarming about: say what to do.
          setLoadError((error as { status?: number } | null)?.status === 401 ? t.documents.signInRequired : t.documents.loadFailed);
        })
        .finally(() => {
          if (requestId === requestIdRef.current) setLoading(false);
        });
    }, trimmedDelay(query));
    return () => window.clearTimeout(timer);
  }, [activeView, query, t.documents.signInRequired, t.documents.loadFailed]);

  // Rich files (PDF/DOCX/...) are parsed by the background worker: refresh until nothing is pending (FR-D3, FR-F20).
  const hasPending = documents.some((doc) => isProcessing(doc.parse_status));
  useEffect(() => {
    if (!hasPending || inTrash) return;
    const timer = window.setInterval(() => {
      const requestId = requestIdRef.current;
      const view = VIEW_TO_API[activeView];
      const trimmed = query.trim();
      const task = trimmed === "" ? api.listDocuments(view) : api.searchDocuments(trimmed, view);
      task
        .then((result) => {
          if (requestId !== requestIdRef.current) return; // a newer tab/search load owns the list
          setDocuments("documents" in result ? result.documents : result.results);
        })
        .catch(() => undefined); // transient: the next tick retries
    }, PARSE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasPending, inTrash, activeView, query]);

  async function handleUpload(file: File | undefined) {
    if (!file) return;
    setStatus(t.documents.uploading);
    try {
      const doc = await api.uploadDocument(file);
      if (activeView === "my") {
        setDocuments((items) => [doc, ...items.filter((item) => item.document_id !== doc.document_id)]);
        setSelectedId(doc.document_id);
      }
      setStatus(isProcessing(doc.parse_status) ? t.documents.uploadProcessing : t.documents.uploadComplete);
    } catch (error) {
      setStatus(reason(error, t.documents.uploadFailed));
    }
  }

  async function handleShare() {
    if (!selectedDocument || !sharePrincipal.trim()) return;
    setStatus(t.documents.sharing);
    try {
      await api.shareDocument(selectedDocument.document_id, { principal: sharePrincipal.trim(), level: "viewer" });
      setStatus(`${t.documents.shared} ${selectedDocument.title}`);
    } catch (error) {
      setStatus(reason(error, t.documents.shareFailed));
    }
  }

  async function handleTrash() {
    if (!selectedDocument) return;
    setStatus(t.documents.movingToTrash);
    try {
      await api.trashDocument(selectedDocument.document_id);
      setDocuments((items) => items.filter((doc) => doc.document_id !== selectedDocument.document_id));
      setSelectedId("");
      setStatus(`${t.documents.trashed}: ${selectedDocument.title}`);
    } catch (error) {
      setStatus(reason(error, t.documents.trashFailed));
    }
  }

  async function handleRestore() {
    if (!selectedDocument) return;
    try {
      await api.restoreDocument(selectedDocument.document_id);
      setDocuments((items) => items.filter((doc) => doc.document_id !== selectedDocument.document_id));
      setSelectedId("");
      setStatus(`${t.documents.restored}: ${selectedDocument.title}`);
    } catch (error) {
      setStatus(reason(error, t.documents.restoreFailed));
    }
  }

  const message = loadError || status;

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.documents.title}</h1>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div role="tablist" className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={activeView === tab.key}
              onClick={() => setActiveView(tab.key)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${
                activeView === tab.key
                  ? "bg-blue-100 text-blue-800"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="search"
            role="searchbox"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t.documents.search}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t.documents.upload}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          aria-label={t.documents.upload}
          className="sr-only"
          onChange={(event) => void handleUpload(event.target.files?.[0])}
        />
        {inTrash ? (
          <button
            type="button"
            onClick={handleRestore}
            disabled={!selectedDocument}
            className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {t.documents.restore}
          </button>
        ) : (
          <>
            <label className="sr-only" htmlFor="share-principal">Share principal</label>
            <input
              id="share-principal"
              aria-label="Share principal"
              value={sharePrincipal}
              onChange={(event) => setSharePrincipal(event.target.value)}
              placeholder={t.documents.shareWith}
              className="rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={handleShare}
              disabled={!selectedDocument || !sharePrincipal.trim()}
              className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {t.documents.share}
            </button>
            <button
              type="button"
              onClick={handleTrash}
              disabled={!selectedDocument}
              className="rounded border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              {t.documents.moveToTrash}
            </button>
          </>
        )}
      </div>

      {message ? <p role="status" className="mb-3 text-sm text-gray-700">{message}</p> : null}

      <div className="rounded-lg border border-gray-200 p-8 text-center text-gray-500">
        {loading ? <p>{t.documents.loading}</p> : null}
        {!loading && documents.length ? (
          <ul className="space-y-2 text-left">
            {documents.map((doc) => (
              <li key={doc.document_id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(doc.document_id)}
                  className={`w-full rounded border px-3 py-2 text-left ${selectedDocument?.document_id === doc.document_id ? "border-blue-400 bg-blue-50" : "border-gray-200"}`}
                >
                  <span className="font-medium text-gray-900">{doc.title}</span>
                  <span className="ml-2 text-xs text-gray-500">{doc.status}</span>
                  {parseBadge(doc.parse_status, t.documents) ? (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                      {parseBadge(doc.parse_status, t.documents)}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {!loading && documents.length === 0 && !loadError ? (inTrash ? t.documents.trashEmpty : t.documents.noDocuments) : null}
      </div>
    </section>
  );
}

const PARSE_POLL_MS = 3000;

// "pending" = queued for the worker; "indexing" = parsed but not searchable yet. Both mean: not ready, check again soon.
function isProcessing(parseStatus: string): boolean {
  return parseStatus === "pending" || parseStatus === "indexing";
}

function parseBadge(parseStatus: string, labels: { parsePending: string; parseFailed: string; parseBlocked: string }): string {
  if (isProcessing(parseStatus)) return labels.parsePending;
  if (parseStatus === "failed") return labels.parseFailed;
  if (parseStatus === "skipped") return labels.parseBlocked;
  return "";
}

function trimmedDelay(query: string): number {
  return query.trim() === "" ? 0 : 250;
}
