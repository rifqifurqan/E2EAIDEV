/**
 * Typed API client for E2EAIDEV backend (/api/v1).
 * Targets endpoints already implemented in apps/api.
 * No real secrets — base URL is configurable, auth uses existing cookie/session.
 */

const API_BASE = "/api/v1";

// ─── Types ──────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  display_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface LoginResponse {
  user_id: string;
  csrf_token: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  document_id: string;
  version_id: string;
  chunk_id: string;
  page: number | null;
  section: string | null;
}

export interface MessageResponse {
  answer: string;
  citations: Citation[];
}

export interface FeedbackInput {
  rating: "up" | "down";
  correction?: string;
}

export type ChatScope =
  | "all"
  | "this_document"
  | "my_documents"
  | "shared_with_me"
  | "my_team";

export interface Document {
  document_id: string;
  title: string;
  sensitivity: string;
  status: string;
  parse_status: string;
  scan_status: string;
}

export interface ShareInput {
  principal: string;
  level: "viewer" | "editor" | "owner";
}

export interface EvalDataset {
  id: string;
  name: string;
  version: number;
  items: unknown[];
}

export interface EvalRun {
  id: string;
  adapter: string;
  status: string;
  metrics: Record<string, number>;
}

export interface Bot {
  id: string;
  name: string;
}

export interface BotBundle {
  id: string;
  version: number;
  status: string;
}

export interface DeactivateInput {
  transfer_to_id: string;
}

export interface DeactivateResponse {
  status: string;
  documents_transferred: number;
  folders_transferred: number;
  sessions_purged: number;
}

// ─── Fetch helper ───────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    public title: string,
    public detail?: string,
  ) {
    super(`${status} ${title}: ${detail ?? ""}`);
    this.name = "ApiError";
  }
}

interface FetchOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  csrfToken?: string;
}

async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {}, csrfToken } = opts;

  const reqHeaders: Record<string, string> = {
    Accept: "application/json",
    ...headers,
  };

  if (body !== undefined) {
    reqHeaders["Content-Type"] = "application/json";
  }
  if (csrfToken) {
    reqHeaders["X-CSRF-Token"] = csrfToken;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: reqHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });

  if (!res.ok) {
    const problem = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      (problem as Record<string, string>).title ?? res.statusText,
      (problem as Record<string, string>).detail,
    );
  }

  return (await res.json()) as T;
}

// ─── Endpoint paths (exported for testing) ──────────────────────────────

export const ENDPOINTS = {
  health: "/health",
  ready: "/ready",
  login: "/auth/login",
  logout: "/auth/logout",
  me: "/me",
  conversations: "/chat/conversations",
  conversation: (id: string) => `/chat/conversations/${id}`,
  messages: (convId: string) => `/chat/conversations/${convId}/messages`,
  feedback: (msgId: string) => `/messages/${msgId}/feedback`,
  stop: (msgId: string) => `/messages/${msgId}/stop`,
  ask: "/chat/ask",
  documents: "/documents",
  document: (id: string) => `/documents/${id}`,
  documentShares: (id: string) => `/documents/${id}/shares`,
  documentSensitivity: (id: string) => `/documents/${id}/sensitivity`,
  documentRestore: (id: string) => `/documents/${id}/restore`,
  visibleChunks: "/documents/visible-chunks",
  evalDatasets: "/evals/datasets",
  evalRuns: "/evals/runs",
  bots: "/bots",
  bot: (id: string) => `/bots/${id}`,
  botBundles: (botId: string) => `/bots/${botId}/bundles`,
  botRollback: (botId: string, bundleId: string) =>
    `/bots/${botId}/bundles/${bundleId}/rollback`,
  botGrants: (botId: string) => `/bots/${botId}/grants`,
  botScope: (botId: string) => `/bots/${botId}/scope`,
  botAsk: (botId: string) => `/bots/${botId}/ask`,
  deactivateUser: (userId: string) => `/users/${userId}/deactivate`,
} as const;

// ─── Client functions ───────────────────────────────────────────────────

export const api = {
  // Health
  health: () => apiFetch<HealthResponse>(ENDPOINTS.health),
  ready: () => apiFetch<HealthResponse>(ENDPOINTS.ready),

  // Auth
  login: (input: LoginInput) =>
    apiFetch<LoginResponse>(ENDPOINTS.login, {
      method: "POST",
      body: input,
    }),
  logout: (csrfToken: string) =>
    apiFetch<{ status: string }>(ENDPOINTS.logout, {
      method: "POST",
      csrfToken,
    }),
  me: () => apiFetch<MeResponse>(ENDPOINTS.me),

  // Chat
  listConversations: (search?: string) => {
    const qs = search ? `?search=${encodeURIComponent(search)}` : "";
    return apiFetch<{ conversations: Conversation[] }>(
      `${ENDPOINTS.conversations}${qs}`,
    );
  },
  createConversation: (title: string) =>
    apiFetch<Conversation>(ENDPOINTS.conversations, {
      method: "POST",
      body: { title },
    }),
  renameConversation: (id: string, title: string) =>
    apiFetch<Conversation>(ENDPOINTS.conversation(id), {
      method: "PATCH",
      body: { title },
    }),
  deleteConversation: (id: string) =>
    apiFetch<{ status: string }>(ENDPOINTS.conversation(id), {
      method: "DELETE",
    }),
  sendMessage: (
    convId: string,
    question: string,
    scope: ChatScope = "all",
    documentId?: string,
  ) =>
    apiFetch<MessageResponse>(ENDPOINTS.messages(convId), {
      method: "POST",
      body: { question, scope, document_id: documentId },
    }),
  recordFeedback: (msgId: string, input: FeedbackInput) =>
    apiFetch<{ status: string; rating: string }>(ENDPOINTS.feedback(msgId), {
      method: "POST",
      body: input,
    }),
  stopMessage: (msgId: string) =>
    apiFetch<{ status: string; stop_reason: string }>(ENDPOINTS.stop(msgId), {
      method: "POST",
    }),
  ask: (question: string, scope: ChatScope = "all", documentId?: string) =>
    apiFetch<MessageResponse>(ENDPOINTS.ask, {
      method: "POST",
      body: { question, scope, document_id: documentId },
    }),

  // Documents
  uploadDocument: async (file: File): Promise<Document> => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}${ENDPOINTS.documents}`, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
    });
    if (!res.ok) {
      const problem = await res.json().catch(() => ({}));
      throw new ApiError(
        res.status,
        (problem as Record<string, string>).title ?? res.statusText,
        (problem as Record<string, string>).detail,
      );
    }
    return (await res.json()) as Document;
  },
  shareDocument: (docId: string, input: ShareInput) =>
    apiFetch<{ status: string }>(ENDPOINTS.documentShares(docId), {
      method: "POST",
      body: input,
    }),
  setSensitivity: (docId: string, sensitivity: string) =>
    apiFetch<{ status: string; sensitivity: string }>(
      ENDPOINTS.documentSensitivity(docId),
      { method: "PATCH", body: { sensitivity } },
    ),
  trashDocument: (docId: string) =>
    apiFetch<{ status: string }>(ENDPOINTS.document(docId), {
      method: "DELETE",
    }),
  purgeDocument: (docId: string) =>
    apiFetch<{ status: string }>(`${ENDPOINTS.document(docId)}?permanent=true`, {
      method: "DELETE",
    }),
  restoreDocument: (docId: string) =>
    apiFetch<{ status: string }>(ENDPOINTS.documentRestore(docId), {
      method: "POST",
    }),
  visibleChunks: () =>
    apiFetch<{ chunks: unknown[] }>(ENDPOINTS.visibleChunks),

  // Evals
  createDataset: (name: string, source: string, items: unknown[]) =>
    apiFetch<EvalDataset>(ENDPOINTS.evalDatasets, {
      method: "POST",
      body: { name, source, items },
    }),
  runEval: (datasetId: string, adapter: string) =>
    apiFetch<EvalRun>(ENDPOINTS.evalRuns, {
      method: "POST",
      body: { dataset_id: datasetId, adapter },
    }),

  // Bots
  createBot: (name: string) =>
    apiFetch<Bot>(ENDPOINTS.bots, { method: "POST", body: { name } }),
  releaseBundle: (botId: string, bundle: Record<string, unknown>) =>
    apiFetch<BotBundle>(ENDPOINTS.botBundles(botId), {
      method: "POST",
      body: { bundle },
    }),
  rollbackBundle: (botId: string, bundleId: string) =>
    apiFetch<BotBundle>(ENDPOINTS.botRollback(botId, bundleId), {
      method: "POST",
    }),
  grantBotAccess: (botId: string, input: ShareInput) =>
    apiFetch<{ principal: string; level: string }>(
      ENDPOINTS.botGrants(botId),
      { method: "POST", body: input },
    ),
  setBotScope: (
    botId: string,
    documentIds: string[],
    folderIds: string[],
  ) =>
    apiFetch<{ status: string }>(ENDPOINTS.botScope(botId), {
      method: "PUT",
      body: { document_ids: documentIds, folder_ids: folderIds },
    }),
  askBot: (botId: string, question: string) =>
    apiFetch<MessageResponse>(ENDPOINTS.botAsk(botId), {
      method: "POST",
      body: { question },
    }),

  // Admin
  deactivateUser: (userId: string, input: DeactivateInput) =>
    apiFetch<DeactivateResponse>(ENDPOINTS.deactivateUser(userId), {
      method: "POST",
      body: input,
    }),
};
