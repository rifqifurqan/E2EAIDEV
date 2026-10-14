# UAT Bug List — E2EAIDEV Live Web

Date: 2026-10-14 (run 14)
Latest result: full v5 **37/0**, ops/admin **14/0**, session expiry **7/0**, admin-mutation **9/0**, mobile-nav **9/0**, and post-build full v5 **37/0**. Evidence `e2eaidev-uat5-1791986045196`, `e2eaidev-uat-ops-1791986161370`, `e2eaidev-uat-session-1791986197056`, `e2eaidev-uat-admin-1791986218207`, `e2eaidev-uat-mobile-1791986240229`, and `e2eaidev-uat5-1791986468896` under Hermes scratch (`C:/Users/riqan/AppData/Local/hermes/cache/scratch/`). No same-run product-code bug was found.

## Open (prioritized)

None verified open. Run 14 found no product-code bug; web :13000 was not running at the start of the sweep, and starting `pnpm dev` after removing `.next` restored health. Runs 13, 12 and 11 also found no product-code bug. Run 10 found no product-code bug after recovering the hung local web dev server. Run 9 fixed UAT-AUTH-002 (below); run 8 fixed UAT-CHAT-007 (below). Run 7 hardened one intermittent case (UAT-DOC-006 below). Candidates not yet exercised in a headed run: see "Not tested" in UAT_LIVE_WEB.md.

## Fixed in run 9

| ID | Sev | Problem (reproduced live) | Fix | Proof |
|---|---|---|---|---|
| UAT-AUTH-002 | Medium | When the session cookie expired while a page was open, the header kept saying "Signed in as andi@…" and chat showed a bare "Not authenticated"; after signing in again Documents still said "Please sign in to see your documents." until a manual reload | `apiFetch` (and upload) dispatch `e2eai:session-expired` on a 401 from an authenticated call (not login/logout//me); `AppShell` drops the session, shows the login form with "Session expired. Please sign in again." (EN/ID) and remounts page content after the next successful sign-in | `api-client.test.ts` (3 new, RED then GREEN), `app-shell.test.tsx` (2 new, RED then GREEN); headed `e2eaidev_uat_session.js` 3 FAIL -> 8/0 |

One-off unexplained: the first v5 run of the tick ended signed out on `/data` mid-chat (10/2); the immediate rerun was 37/0 and nothing reproduced it. Logged, not claimed as fixed. The session-expiry fix at least makes that situation self-explanatory in the UI.

## Fixed in run 8

| ID | Sev | Problem (observed live) | Fix | Proof |
|---|---|---|---|---|
| UAT-CHAT-007 | Medium | With a temporary per-user quota (1 req/min, then 1 token/day) the chat showed "Rate limit exceeded" / "Token quota exceeded", but the question stayed in the thread as a User bubble with no answer and the input was cleared, so the user had to retype it. | On a send failure the unanswered bubble is removed and the question is restored to the input (unless the user has typed something new). | `chat-screen.test.tsx` "restores the question and drops the unanswered bubble when sending fails" (RED then GREEN); headed `e2eaidev_uat_quota.js` 6/0 incl. `rate-limit-failed-question-restored-to-input`, `rate-limit-no-unanswered-bubble`. |

Also verified OK in run 8 (no bug): storage quota 413 shows "Storage quota exceeded" in Documents and nothing is listed; request-rate 429 and token-quota 429 messages are readable and the input stays usable. Test-data hygiene: the quota script sets a temporary user policy on Andi and always clears it (policy rows 0 afterwards).

## Fixed in run 7

| ID | Sev | Problem (observed live) | Fix | Proof |
|---|---|---|---|---|
| UAT-DOC-006 | Medium | One headed run showed `500 POST /api/v1/documents` ("Internal Server Error" in the Documents status line). Not reproducible afterwards (3 API probes, 2 more headed runs, a forced bge-m3 cold start that took ~10 s but returned 200). Most likely LiteLLM answered 500 while the Ollama embedding runner reloaded; `post_json_with_retry` only retried 429/502/503/504, so the 500 surfaced as an unhandled error | `RETRY_STATUS` now includes 500 (embedding/chat/rerank calls are idempotent); persistent failure ends as the existing clear 503 | `test_resilient_http_nfr19.py::test_embedder_retries_gateway_500_then_succeeds` (RED: HTTPStatusError, GREEN) and `::test_embedder_persistent_gateway_error_is_a_clear_502_not_unhandled` |

Root cause is inferred, not captured: no LiteLLM/Ollama error was in the logs at the time of the check. Treat as hardening; re-open if a 500 on upload recurs.

## Fixed in run 6

| ID | Sev | Problem (reproduced live) | Fix | Proof |
|---|---|---|---|---|
| UAT-CHAT-006 | Low | Citations panel was a flat list of every citation across the whole conversation, repeating documents after several answers | Panel shows only the newest assistant answer's citations; earlier assistant answers keep their own citations inline under that answer (so history citations are not lost) | `chat-screen.test.tsx` RED (1 failed) then GREEN (20 passed); live v5 `chat-citations-panel-shows-latest-answer-only` and `chat-history-keeps-citation` PASS (the first v5 run caught that dropping history citations made `chat-history-keeps-citation` FAIL, hence the inline rendering) |

## Fixed in run 5

| ID | Sev | Problem (reproduced live) | Fix | Proof |
|---|---|---|---|---|
| UAT-ADMIN-001 | Medium | No admin demo account existed, so admin mutation flows could not be UAT'd; the legacy `admin@local` address was also rejected by the API login schema | Added `e2eai-api reset-admin-password [--creds-file PATH]` CLI command: resets or creates/migrates `admin@local.e2eai` with a random password; `--creds-file` writes credentials to a file outside the repo (rejects in-repo paths); no committed secret, no web backdoor | `test_reset_admin_password.py` + adjacent auth/seed tests: 17 passed; `app-shell.test.tsx`: 15 passed; live admin UAT `e2eaidev-uat-admin-1791966227548`: 9/0 |

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

- Run 14 environment note: web :13000 was not running at the start of the cron tick. Removing `.next` and starting `pnpm dev` restored web `/` and `/api/v1/health` to 200. No product bug was verified.

- Run 13 environment note: web :13000 was not running at the start of the cron tick. Removing `.next` and starting `pnpm dev` restored web `/` and `/api/v1/health` to 200. No product bug was verified.

- Run 12 environment note: web :13000 was not running at the start of the cron tick. Removing `.next` and starting `pnpm dev` restored web `/` and `/api/v1/health` to 200. No product bug was verified.

- Run 11 environment note: web :13000 was simply down at the start of the cron tick. Starting `pnpm dev` in a PTY after removing `.next` restored web `/` and `/api/v1/health` to 200. No product bug was verified.

- Run 10 environment note: the Next dev listener on :13000 can accept TCP and hang all HTTP requests after `.next` churn. Recovery remains: stop the stale listener, remove `.next`, restart `pnpm dev`, then verify web `/` and `/api/v1/health` before running UAT. This was an environment issue, not a verified product-code bug.

- Run 7 test-data note: UAT probes created `probe*.txt` documents whose contents ("12 hari") polluted Andi's "everything I can access" scope and made the chat UAT fail until they were moved to Trash. UAT scripts should upload uniquely worded docs and trash their own uploads.
- First upload after the embedding model is idle takes ~10 s (bge-m3 cold start); the UI shows no progress indicator during that time.

- Convert the scratch UAT scripts into a repo-maintained Playwright suite with a credential-free way to obtain a demo login.
- The relevance floor (0.30) was chosen from observed bge-m3 scores (related ≈ 0.71, unrelated Mars ≈ 0.24). Re-tune with the retrieval-metrics lab if recall drops on a real corpus; set `retrieval.min_relevance: 0` to disable.
- The "Board review" conversation in Andi's list is earlier test data in the shared dev DB, not something the UI created.
