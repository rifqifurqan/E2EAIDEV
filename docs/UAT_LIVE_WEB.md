# Live Web UAT — E2EAIDEV

Date: 2026-10-14 (run 7)
Tester: Hermes Agent + Claude Code review, headed Playwright / Chrome (non-headless, slowMo 50–60)
Target web: http://127.0.0.1:13000 · Target API: http://127.0.0.1:8000
Demo user: `andi@demo.e2eai` (not an org admin). Its local password lives only in Hermes scratch, never in the repo.
Admin user: `admin@local.e2eai` (org admin). Reset with `e2eai-api reset-admin-password --creds-file <path-outside-repo>`. The generated password is never committed.

## Evidence (Hermes scratch, `C:/Users/riqan/AppData/Local/hermes/cache/scratch/`)

- Run 1 (earlier, 22/22): `e2eaidev-uat-1791957118046`
- Run 2 before fixes, v2 script: `e2eaidev-uat2-1791957806874` (**17 pass / 13 fail**; a few fails were script-order mistakes, the rest were real bugs, see UAT_BUGS.md)
- Run 2 after fixes, v3 script: `e2eaidev-uat3-1791960461338` (**36 pass / 0 fail**), screenshots `01-…24-*.png`
- Run 2 after fixes, original script: `e2eaidev-uat-1791960549558` (**22 pass / 0 fail**)
- Run 3 after UAT-CHAT-005 fix, v4 script: `e2eaidev-uat4-1791961850058` (**37 pass / 0 fail**), screenshots `01-…25-*.png`; visual spot-check `08-chat-stop.png` shows the green "Generation stopped." notice and the expected `cuti-uat.txt · page 1` citation.
- Run 4 after UAT-NAV-001 fix: full v4 script `e2eaidev-uat4-1791963285993` (**37 pass / 0 fail**) plus mobile-nav script `e2eaidev-uat-mobile-1791963402626` (**9 pass / 0 fail**), screenshots `01-mobile-home-nav.png` through `04-mobile-admin.png`; visual spot-check `01-mobile-home-nav.png` shows Documents / Chat / Admin visible on a 390 px-wide viewport.
- Run 5 after UAT-ADMIN-001 fix: full v4 script `e2eaidev-uat4-1791966120479` (**37 pass / 0 fail**), mobile-nav script `e2eaidev-uat-mobile-1791966218787` (**9 pass / 0 fail**), and admin-mutation script `e2eaidev-uat-admin-1791966227548` (**9 pass / 0 fail**). Admin evidence includes login as `admin@local.e2eai`, org snapshot load, create division, create team, create user, add team member, and grant evaluator role.
- Run 6 after UAT-CHAT-006 fix: full v5 script `e2eaidev-uat5-1791967780471` (**37 pass / 0 fail**), mobile-nav script `e2eaidev-uat-mobile-1791967554354` (**9 pass / 0 fail**), admin-mutation script `e2eaidev-uat-admin-1791967877237` (**9 pass / 0 fail**). v5 = v4 with the citation check changed to assert the panel shows only the latest answer (`chat-citations-panel-shows-latest-answer-only`). Environment: web on :13000 was hung (accepting TCP, never answering HTTP); fixed by SIGTERM of the stale dev process, wiping `.next`, restarting `pnpm dev`.
- Run 7: baseline v5 run -> 34/3 (one `500 POST /api/v1/documents` on upload; evidence `e2eaidev-uat5-1791975370681`); second run 34/3 (chat failed because leftover probe docs said "12 hari"; `e2eaidev-uat5-1791975714101`); after trashing probe docs: v5 **37/0** twice (`e2eaidev-uat5-1791975882751`, `e2eaidev-uat5-1791975981683`). New ops script `e2eaidev_uat_ops.js` (admin): **14/0** (`e2eaidev-uat-ops-1791976353799`) covering Operate incident report (empty-title disabled, create, appears in list, form cleared), incident transition, Improve/Admin pages as admin, empty-file upload (clear 400 message), binary upload (no crash), admin sign-out. The first ops run had 2 FAILs that were my script reading the page before the ~5.5 s report round trip finished; waiting for the form to clear made them pass.
- Scripts: `e2eaidev_uat_ops.js` (admin Operate/Improve/Admin/upload edge cases), `e2eaidev_uat_v5.js` (current full run), `e2eaidev_uat_live.js` (happy path), `e2eaidev_uat_v2.js` (negative paths, found run-2 bugs), `e2eaidev_uat_v3.js` (run-2 regression), `e2eaidev_uat_v4.js` (run-3 Stop regression). Not yet committed as a repo suite (they need the scratch-held demo password).

## Prerequisites verified

- API `/api/v1/health` 200; web `/` 200; web-origin proxy `/api/v1/health` 200.
- Containers up: postgres (healthy), valkey (healthy), openfga, seaweedfs, litellm, e2eai-ollama-1.
- Environment issue found and fixed: `/` returned **500** (`Cannot find module './687.js'`) because a production `pnpm build` had overwritten `.next` under the running dev server. Fix: stop dev server, remove `.next`, restart `pnpm dev`. Rule: never run `pnpm build` while `pnpm dev` serves from the same `.next`; after a build, wipe `.next` and restart dev.
- Environment issue found and fixed: Andi's chat returned **429 "Token budget exceeded"** for a 10-word question. Cause: a leftover quota policy row (5 req/min, 500 tokens/day) written by `test_quota_policy_crud_and_lookup` against the shared dev DB. The two rows were removed and the test now cleans up after itself.

## PASS/FAIL matrix (final, v3 + baseline)

Auth
- PASS signed-out Documents page says "Please sign in to see your documents." (was a misleading "Could not load documents" over an empty library)
- PASS wrong password shows "Invalid email or password"
- PASS login with Enter key; sign-in form disappears after login; Sign out button present
- PASS reload keeps the session and Sign out still works (csrf token now returned by `/me`)
- PASS sign out ends the session (`/me` → 401) and shows the form again

Documents
- PASS upload completes and lists the file (EN and ID status text)
- PASS share with `user:not-a-uuid` is rejected with "Invalid principal" (was reported as success)
- PASS "Move to Trash" removes the document with a clear message; Trash tab lists it; Restore brings it back
- PASS persistence after reload, backend search, Shared/Team tabs (run 1)

Chat
- PASS answer from the uploaded document with citation (ID question, ID source)
- PASS unrelated question ("Siapa presiden Mars tahun 3000?") → "Saya tidak menemukan dokumen yang relevan…" with **no** new citation
- PASS conversations listed by title (not UUID), persisted after reload, history + citation load on click
- PASS citations panel shows only the latest answer's citations; earlier answers keep theirs inline (run 6)
- PASS Yes/No feedback sends `POST /messages/{id}/feedback` and confirms
- PASS Stop sends `POST /messages/{id}/stop` for the latest assistant message and shows the localized stop notice (run 3 v4); component test also covers in-flight abort/drop.

Locale / a11y / responsive navigation
- PASS Indonesian choice survives full-page navigation (localStorage), `<html lang>` follows it
- PASS header status, Sign out, upload status are localized
- PASS first Tab stop is the skip link
- PASS mobile-width (390 px) feature navigation keeps Documents, Chat and Admin visible and navigable; ID labels also localize (`Dokumen`, `Obrolan`, `Admin`)

Lifecycle pages (Plan, Data, Build, Test, Release, Operate, Improve, Admin)
- PASS all render in ID without error; a non-admin sees admin-only notices instead of dead forms
- PASS plan submit, model register, config export through the proxy (run 1)

Health
- PASS no 5xx; PASS no unexpected 4xx (expected: 401 before login, 403 admin-only, 422 invalid share); PASS no unexpected JS errors

## Fixes made from this run (all TDD, see UAT_BUGS.md)

Run 6: Chat citations are per answer (UAT-CHAT-006). The Citations panel shows only the newest assistant answer's citations; older assistant answers display their own citations inline, so reopened history still shows them. Component tests: new RED/GREEN for the panel and for inline history citations (20 tests in `chat-screen.test.tsx`).

Run 5: Admin login path for UAT. `e2eai-api reset-admin-password --creds-file <path>` resets or creates/migrates `admin@local.e2eai` with a random password and writes credentials to a scratch file outside the repo. No committed secret, no web backdoor; the CLI command refuses to write inside the repo tree. The headed admin UAT now covers admin login, organization snapshot, create division/team/user, add team member, and grant role. The original `admin@local` value was not browser/API-login compatible because Pydantic `EmailStr` rejects addresses without a dotted domain.

Run 4: Mobile feature navigation is now reachable below the `md` breakpoint. App shell renders a dedicated mobile feature nav for Documents / Chat / Admin above the main content while keeping the desktop sidebar at `md` and up; EN/ID landmark labels and link labels are covered by component tests and a headed 390 px Playwright UAT.

Run 3: Chat Stop is now wired to real behavior. The web client creates an `AbortController` for each send, disables Stop when nothing can be stopped, drops a late answer after an abort, calls `api.stopMessage(message_id)` when a stopped/finished assistant message id exists, and uses localized EN/ID status text.

Run 2:

API: principal validation before share; minimum-relevance floor (0.30, `retrieval.min_relevance` in e2eai.yaml); `GET /chat/conversations/{id}/messages`; `message_id` in the chat reply; stored citations keep their document; `view=trash`; `/me` returns the session csrf token.
Web: Sign out and hidden login form; "Move to Trash" label, Trash tab with Restore; chat conversation list/history/feedback; localized status text; locale persistence; sign-in hint for signed-out visitors; API reason shown on share failure.

## Verification gates (this run)

- Run 7: `cd apps/api && uv run pytest -q tests/test_resilient_http_nfr19.py` -> RED 2 failed, GREEN 7 passed; adjacent (resilience, circuit breaker, upload ingest, cited answer, vector store, semantic cache, chat conversations, doc lifecycle, UAT principal/relevance, documents list, quotas, retrieval metrics, metrics) -> 94 passed. Web untouched, so web typecheck/lint/build were not re-run. Live API process was not restarted (process kill blocked in the cron session), so the running server still has the old retry set until its next restart.
- Run 6: `cd apps/web && pnpm vitest run src/components/chat-screen.test.tsx` -> RED 1 failed, then 20 passed; `pnpm vitest run` -> 21 files / 321 tests passed; `pnpm run typecheck` ok; `pnpm run lint` clean; `pnpm run build` ok (then `.next` wiped and dev restarted). Headed Playwright: v5 37/0, mobile 9/0, admin 9/0. Skipped on purpose: full API/CLI suites and `verify-phase-0` (web-only change).

- Run 4: TDD RED `cd apps/web && pnpm vitest run src/components/app-shell.test.tsx` -> 1 failed (`mobile feature navigation` missing). GREEN after the fix -> 15 passed.
- Run 4: Claude Code review of the diff completed successfully; it found no functional regression. Hermes also visually spot-checked `e2eaidev-uat-mobile-1791963402626/01-mobile-home-nav.png`.
- Run 4: headed Playwright v4 UAT (`NODE_PATH=.../e2eaidev-playwright-runtime/node_modules node .../e2eaidev_uat_v4.js`) -> 37 passed / 0 failed; headed mobile-nav UAT (`node .../e2eaidev_uat_mobile_nav.js`) -> 9 passed / 0 failed; no unexpected 5xx/4xx/console errors.

- Run 3: `cd apps/web && pnpm vitest run src/components/chat-screen.test.tsx src/lib/api-client.test.ts` -> 2 files / 32 tests passed.
- Run 3: `cd apps/web && pnpm run typecheck` -> ok.
- Run 3: `cd apps/web && pnpm vitest run && pnpm run lint && pnpm run build` -> 21 files / 318 tests passed; lint clean; production build compiled successfully.
- Run 3: `python scripts/validate_docs.py` -> PASS.
- Run 3: headed Playwright v4 UAT (`NODE_PATH=.../e2eaidev-playwright-runtime/node_modules node .../e2eaidev_uat_v4.js`) -> 37 passed / 0 failed; no unexpected 5xx/4xx/console errors.
- API focused + adjacent: 149 passed (`test_uat_principal_and_relevance.py` 23, quotas, auth, api_keys, chat, cited answer, document lifecycle, share policy/expiry/views, search, guardrails, language, explainability, release bundle, upload ingest, semantic cache, docs, offboarding, retrieval metrics).
- Web: `pnpm vitest run` 21 files / 315 tests; `pnpm run typecheck` ok; `pnpm lint` ok; `pnpm build` ok (then `.next` wiped and dev restarted).
- `python scripts/validate_docs.py` PASS; `docs/openapi.json` + API reference regenerated, contract test passes.
- Intentionally skipped: full API suite, CLI suite, `verify-phase-0` (changes are confined to the touched modules).

## Not tested

- Run 7: Admin offboarding and flywheel *triage actions* (queue was empty, so only page load was verified). Cold-start progress UI for slow first upload.

- Admin offboarding and flywheel triage actions: not exercised (empty queue). Incident report + transition (run 7) and admin org mutations (run 5) are covered.
- Drag-and-drop upload, files over quota, real PDF/DOCX (Docling not installed), screen-reader walkthrough, concurrent sessions, session idle expiry.
- Production server (`pnpm start`); UAT ran against `pnpm dev`.
- Browser UX for rate-limit / token-quota 429 responses.
