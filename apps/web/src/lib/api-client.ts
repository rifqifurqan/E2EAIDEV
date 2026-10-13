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
  /** Live /chat/ask returns the document display name; stored citations carry ids. */
  document?: string;
  document_id?: string;
  version_id?: string;
  chunk_id?: string;
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

export interface UseCaseInput {
  title: string;
  business_owner?: string;
  purpose: string;
  risk_tier?: string;
}

export interface UseCaseResponse {
  id: string;
  title: string;
  status: string;
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

export interface FlywheelItem {
  id: string;
  source: string;
  status: string;
  question: string | null;
  correction: string | null;
  reason: string | null;
  target: string | null;
}

export interface FlywheelQueue {
  by_status: Record<string, number>;
  by_source: Record<string, number>;
  items: FlywheelItem[];
  next_cursor: string | null;
}

export interface AiIncident {
  id: string;
  title: string;
  severity: string;
  status: string;
  postmortem?: Record<string, unknown> | null;
}

export interface ReportIncidentInput {
  title: string;
  severity: "sev1" | "sev2" | "sev3" | "sev4";
  description?: string;
}

export interface PostmortemInput {
  summary: string;
  root_cause: string;
}

export interface IncidentTransition {
  to_status: "triaged" | "fixing" | "fixed" | "released" | "closed";
  fix_notes?: string;
  release_ref?: string;
}

export interface IncidentList {
  incidents: AiIncident[];
  next_cursor: string | null;
}

export interface DueReview {
  document_id: string;
  title: string;
  review_at: string;
  overdue_days: number;
  expires_at: string | null;
}

export interface DueReviewList {
  reviews: DueReview[];
  next_cursor: string | null;
}

export interface ModelVersion {
  name: string;
  version: string;
  parent_version: string | null;
  lineage: Record<string, unknown>;
  eval_scores: Record<string, number>;
  approval_status: string;
  approved_by: string | null;
}

export interface ModelVersionList {
  models: ModelVersion[];
  next_cursor: string | null;
}

export interface BotApproval {
  id: string;
  bot_id: string;
  approval_type: string;
  risk_tier: string;
  status: string;
  rationale: string | null;
  decision_note: string | null;
  requested_by: string | null;
  decided_by: string | null;
  created_at: string | null;
  decided_at: string | null;
}

export interface BotApprovalList {
  items: BotApproval[];
  next_cursor: string | null;
}

export interface EvalRunSummary {
  id: string;
  dataset_id: string | null;
  adapter: string;
  status: string;
  metrics: Record<string, unknown>;
  created_at: string | null;
}

export interface EvalDatasetSummary {
  id: string;
  name: string;
  version: number;
  source: string;
  item_count: number;
  created_at: string | null;
}

export interface EvalDatasetList {
  datasets: EvalDatasetSummary[];
  next_cursor: string | null;
}

export interface EvalRunList {
  runs: EvalRunSummary[];
  next_cursor: string | null;
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
  useCases: "/plan/use-cases",
  configExport: (format: "yaml" | "json" = "yaml") =>
    `/admin/config/export?format=${format}`,
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
  incidents: "/incidents",
  incidentPostmortem: (incidentId: string) => `/incidents/${incidentId}/postmortem`,
  incidentTransition: (incidentId: string) => `/incidents/${incidentId}/transition`,
  flywheel: "/improve/flywheel",
  flywheelExport: "/improve/flywheel/export",
  flywheelTriage: (itemId: string) => `/improve/flywheel/${itemId}/triage`,
  flywheelReeval: (itemId: string) => `/improve/flywheel/${itemId}/reeval`,
  flywheelRelease: (itemId: string) => `/improve/flywheel/${itemId}/release`,
  dueReviews: "/documents/reviews/due",
  documentReviewed: (documentId: string) => `/documents/${documentId}/lifecycle/reviewed`,
  modelRegistry: "/model-registry",
  modelDecision: (name: string, version: string) =>
    `/model-registry/${encodeURIComponent(name)}/${encodeURIComponent(version)}/decision`,
  modelEvalRuns: (name: string, version: string) =>
    `/model-registry/${encodeURIComponent(name)}/${encodeURIComponent(version)}/eval-runs`,
  botApprovals: "/governance/bot-approvals",
  botApprovalDecision: (approvalId: string) => `/governance/bot-approvals/${approvalId}/decisions`,
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

  // Plan
  createUseCase: (input: UseCaseInput) =>
    apiFetch<UseCaseResponse>(ENDPOINTS.useCases, {
      method: "POST",
      body: {
        title: input.title,
        problem: input.purpose,
        users: input.business_owner ? [input.business_owner] : ["business owner"],
        success_metrics: {
          task_success: "Defined during intake",
          deflection: "Defined during intake",
          time_saved: "Defined during intake",
        },
        data_sources: [],
        systems_to_integrate: [],
        risk_tier: input.risk_tier ?? "limited",
      },
    }),

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

  // Operate / Improve (admin-only on the server)
  listIncidents: () => apiFetch<IncidentList>(ENDPOINTS.incidents),
  listIncidentsPage: (cursor: string) =>
    apiFetch<IncidentList>(`${ENDPOINTS.incidents}?cursor=${encodeURIComponent(cursor)}`),
  reportIncident: (input: ReportIncidentInput) =>
    apiFetch<AiIncident>(ENDPOINTS.incidents, { method: "POST", body: input }),
  recordPostmortem: (incidentId: string, input: PostmortemInput) =>
    apiFetch<AiIncident>(ENDPOINTS.incidentPostmortem(incidentId), { method: "POST", body: input }),
  transitionIncident: (incidentId: string, input: IncidentTransition) =>
    apiFetch<AiIncident>(ENDPOINTS.incidentTransition(incidentId), { method: "POST", body: input }),
  listFlywheel: () => apiFetch<FlywheelQueue>(ENDPOINTS.flywheel),
  listFlywheelPage: (cursor: string) =>
    apiFetch<FlywheelQueue>(`${ENDPOINTS.flywheel}?cursor=${encodeURIComponent(cursor)}`),
  exportFlywheel: (target: "eval" | "finetune", name: string) =>
    apiFetch<{ dataset_id: string; name: string; version: number; items: number }>(ENDPOINTS.flywheelExport, {
      method: "POST",
      body: { target, name },
    }),
  triageFlywheelItem: (itemId: string, decision: "accept" | "dismiss", target?: "eval" | "finetune") =>
    apiFetch<FlywheelItem>(ENDPOINTS.flywheelTriage(itemId), {
      method: "POST",
      body: target === undefined ? { decision } : { decision, target },
    }),
  linkFlywheelReeval: (itemId: string, runId: string) =>
    apiFetch<FlywheelItem>(ENDPOINTS.flywheelReeval(itemId), { method: "POST", body: { run_id: runId } }),
  linkFlywheelRelease: (itemId: string, releaseRef: string) =>
    apiFetch<FlywheelItem>(ENDPOINTS.flywheelRelease(itemId), { method: "POST", body: { release_ref: releaseRef } }),

  // Data / Build (signed-in users; scope enforced by the server)
  listDueReviews: () => apiFetch<DueReviewList>(ENDPOINTS.dueReviews),
  listDueReviewsPage: (cursor: string) =>
    apiFetch<DueReviewList>(`${ENDPOINTS.dueReviews}?cursor=${encodeURIComponent(cursor)}`),
  markReviewed: (documentId: string, nextReviewInDays: number) =>
    apiFetch<{ status: string; review_at: string }>(ENDPOINTS.documentReviewed(documentId), {
      method: "POST",
      body: { next_review_in_days: nextReviewInDays },
    }),
  listModels: () => apiFetch<ModelVersionList>(ENDPOINTS.modelRegistry),
  listModelsPage: (cursor: string) =>
    apiFetch<ModelVersionList>(`${ENDPOINTS.modelRegistry}?cursor=${encodeURIComponent(cursor)}`),
  registerModel: (name: string, version: string, parentVersion?: string) =>
    apiFetch<ModelVersion>(ENDPOINTS.modelRegistry, {
      method: "POST",
      body: parentVersion === undefined ? { name, version } : { name, version, parent_version: parentVersion },
    }),
  decideModel: (name: string, version: string, decision: "approved" | "rejected") =>
    apiFetch<ModelVersion>(ENDPOINTS.modelDecision(name, version), {
      method: "POST",
      body: { decision },
    }),
  attachEvalRun: (name: string, version: string, runId: string) =>
    apiFetch<ModelVersion>(ENDPOINTS.modelEvalRuns(name, version), {
      method: "POST",
      body: { run_id: runId },
    }),

  // Release (scope enforced by the server)
  // Test (admin-only on the server)
  listEvalDatasets: () => apiFetch<EvalDatasetList>(ENDPOINTS.evalDatasets),
  listEvalDatasetsPage: (cursor: string) =>
    apiFetch<EvalDatasetList>(`${ENDPOINTS.evalDatasets}?cursor=${encodeURIComponent(cursor)}`),
  listEvalRuns: () => apiFetch<EvalRunList>(ENDPOINTS.evalRuns),
  listEvalRunsPage: (cursor: string) =>
    apiFetch<EvalRunList>(`${ENDPOINTS.evalRuns}?cursor=${encodeURIComponent(cursor)}`),

  listBotApprovals: () => apiFetch<BotApprovalList>(ENDPOINTS.botApprovals),
  listBotApprovalsPage: (cursor: string) =>
    apiFetch<BotApprovalList>(`${ENDPOINTS.botApprovals}?cursor=${encodeURIComponent(cursor)}`),
  requestBotApproval: (botId: string, rationale?: string) =>
    apiFetch<BotApproval>(ENDPOINTS.botApprovals, {
      method: "POST",
      body: rationale === undefined ? { bot_id: botId } : { bot_id: botId, rationale },
    }),
  decideBotApproval: (approvalId: string, decision: "approved" | "rejected") =>
    apiFetch<BotApproval>(ENDPOINTS.botApprovalDecision(approvalId), {
      method: "POST",
      body: { decision },
    }),

  // Admin
  deactivateUser: (userId: string, input: DeactivateInput) =>
    apiFetch<DeactivateResponse>(ENDPOINTS.deactivateUser(userId), {
      method: "POST",
      body: input,
    }),
};
