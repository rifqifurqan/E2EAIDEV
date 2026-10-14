# UAT Bug List — E2EAIDEV Live Web

Date: 2026-10-14 (run 4)
Latest result: full v4 **37/0** plus mobile-nav **9/0**. Evidence `e2eaidev-uat4-1791963285993` and `e2eaidev-uat-mobile-1791963402626` under Hermes scratch (`C:/Users/riqan/AppData/Local/hermes/cache/scratch/`). Previous passing evidence: `e2eaidev-uat4-1791961850058`, `e2eaidev-uat3-1791960461338` and `e2eaidev-uat-1791960549558`. Before-fix evidence: `e2eaidev-uat2-1791957806874`.

## Open (prioritized)

1. **UAT-ADMIN-001 — No admin demo account, so admin mutation flows cannot be UAT'd.** Severity: Medium (coverage gap). Add a documented admin login path for UAT.
2. **UAT-CHAT-006 — Citations panel is a flat list across the whole conversation.** Severity: Low. After several answers it repeats documents; it should be per answer. (The "no citation for an unrelated question" case is correct and verified.)

## Fixed in run 4

| ID | Sev | Problem (reproduced live) | Fix | Proof |
|---|---|---|---|---|
| UAT-NAV-001 | Low–Medium | On narrow/mobile widths the desktop sidebar is hidden below `md`, so Documents / Chat / Admin navigation disappeared from the viewport | App shell now renders a dedicated mobile feature nav for Documents / Chat / Admin above main content below `md`, with EN/ID labels; desktop sidebar remains for `md` and up | `app-shell.test.tsx` RED then GREEN; headed mobile Playwright UAT at 390 px (`e2eaidev-uat-mobile-1791963402626`) 9/0; full v4 UAT still 37/0 |

## Fixed in run 3

| ID | Sev | Problem (reproduced live) | Fix | Proof |
|---|---|---|---|---|
| UAT-CHAT-005 | Medium | Stop button only set local English text (`Stopped`); it did not cancel an in-flight request or call `POST /messages/{id}/stop` for an assistant message | Chat now creates an `AbortController` for each send, disables Stop when there is nothing to stop, drops an aborted late answer, calls `api.stopMessage(message_id)` when a stopped/finished assistant message id exists, and shows localized EN/ID notices | `chat-screen.test.tsx` (in-flight abort/drop + finished-answer stop), `api-client.test.ts`, and live v4 `chat-stop-calls-stop-endpoint-and-shows-notice` (POST observed, green notice visible) |

## Fixed in run 2

| ID | Sev | Problem (reproduced live) | Fix | Proof |
|---|---|---|---|---|
| UAT-DOC-005 | High | Share with `user:not-a-uuid` showed "Shared …" and wrote a junk OpenFGA tuple + read-index row | `validate_principal` runs before any read/write (422 "Invalid principal"); UI shows the API title | `test_uat_principal_and_relevance.py` (parametrized cases), v3 `share-invalid-principal-shows-clear-error` |
| UAT-CHAT-002 | High | An unrelated question got the nearest chunk as the answer **with a citation** (Mars question answered with the leave policy) | minimum cosine similarity 0.30 for dense retrieval, configurable `retrieval.min_relevance` | `test_unrelated_question_gets_no_context…`, v3 `chat-unrelated-question-*` |
| UAT-CHAT-001 | High | Conversation list showed the raw UUID and was empty after reload; asking never used a conversation, so nothing was saved | list on mount, show title, first question creates a conversation named after it, later questions reuse it | chat-screen tests + v3 `chat-conversation-*` |
| UAT-CHAT-003 | Medium | Yes/No feedback buttons were decorative | send feedback for the latest assistant message (API now returns `message_id`) | chat-screen test, `test_send_message_returns_message_id…`, v3 `chat-feedback-sent` |
| UAT-CHAT-004 | Medium | No way to reopen a past conversation | `GET /chat/conversations/{id}/messages` (owner-scoped, 404 for others); citations now store their document | API test + v3 `chat-history-*` |
| UAT-AUTH-001 | High | After login the form stayed visible next to "Signed in as …"; no way to sign out | form replaced by status + Sign out; `/me` returns the csrf token so Sign out works after reload | app-shell tests, `test_me_returns_session_csrf_token…`, v3 sign-out checks |
| UAT-DOC-006 | High | The button labelled "Revoke Access" actually **moved the document to trash** (DELETE) and there was no trash view or restore | renamed "Move to Trash"; new Trash tab (`view=trash`, owner-only) with Restore | `test_trash_view_lists_only_the_owners…`, documents-screen tests, v3 trash/restore checks |
| UAT-DOC-007 | Low | Signed-out Documents showed "Could not load documents" and "No documents found." | "Please sign in to see your documents." on 401 | documents-screen test, v3 `unauth-documents-shows-sign-in-hint` |
| UAT-I18N-001 | Medium | In Indonesian mode upload/share/trash status and login text stayed English | moved to the EN/ID dictionaries | documents-screen / app-shell tests, v3 `id-locale-*` |
| UAT-I18N-002 | Medium | Choosing Bahasa Indonesia was lost on every page navigation (nav uses full-page links) | persist in localStorage, restore after mount, sync `<html lang>` | `i18n/context.test.tsx`, v3 `id-locale-persists-across-full-navigation` |
| UAT-QUOTA-001 | High (blocked chat) | Andi's chat returned 429 "Token budget exceeded" for a short question: `test_quota_policy_crud_and_lookup` left a 5 req/min / 500 tokens/day policy in the shared dev DB | the test deletes the policies it creates; the two leftover rows were removed | `test_us_quotas_rate_limits.py` (9 pass), DB shows 0 policies |
| ENV-WEB-001 | High (blocked UAT) | `/` returned 500 `Cannot find module './687.js'` after a production build overwrote `.next` under `pnpm dev` | wipe `.next`, restart dev; rule noted in UAT_LIVE_WEB.md | `/`, `/documents`, `/chat` return 200, UAT passes |

Earlier fixed (run 1): UAT-DOC-001 (list lost on reload), UAT-DOC-002 (search not wired), UAT-DOC-003 (tabs not wired), UAT-OPS-001 (dead incident form for non-admin).

## Watch list

- Convert the scratch UAT scripts into a repo-maintained Playwright suite with a credential-free way to obtain a demo login.
- The relevance floor (0.30) was chosen from observed bge-m3 scores (related ≈ 0.71, unrelated Mars ≈ 0.24). Re-tune with the retrieval-metrics lab if recall drops on a real corpus; set `retrieval.min_relevance: 0` to disable.
- The "Board review" conversation in Andi's list is earlier test data in the shared dev DB, not something the UI created.
