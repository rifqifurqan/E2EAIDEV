# Live Web UAT — E2EAIDEV

Date: 2026-10-14 (run 16)
Tester: Hermes Agent, headed Playwright / Chrome (non-headless, slowMo 50–60)
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
- Run 9 (session expiry, UAT-AUTH-002): first v5 run of the tick -> 10/2 (chat flow found the app on `/data`, signed out, mid-run; not reproduced: immediate rerun v5 **37/0**, `e2eaidev-uat5-1791978980164`; failing run `e2eaidev-uat5-1791978847050`). New script `e2eaidev_uat_session.js` (cookies cleared while chat is open): before fix header kept "Signed in as" over "Not authenticated" and Documents kept "Please sign in" after re-login (`e2eaidev-uat-session-1791979121346`, 3 FAIL). After fix: session script **8/0** (`e2eaidev-uat-session-1791979414092`), v5 **37/0** (`e2eaidev-uat5-1791979438101`), mobile-nav **9/0** (`e2eaidev-uat-mobile-1791979549815`), admin **9/0** (`e2eaidev-uat-admin-1791979560248`). Screenshots `01-chat-send-after-expiry.png`, `03-relogin.png`.
- Run 10 (cron live UAT sweep): first v5 run found the web dev listener on :13000 accepting TCP but never answering HTTP; v5 failed early at `/documents` with a Playwright `networkidle` timeout (`e2eaidev-uat5-1791980341000`, 0/1). The stale listener PID 19404 could not be stopped with non-force `taskkill`; it was terminated via Windows API, `.next` was removed with Python, and `pnpm dev` was restarted. After recovery: v5 **37/0** (`e2eaidev-uat5-1791980528893`), ops/admin **14/0** (`e2eaidev-uat-ops-1791980648911`), session expiry **7/0** (`e2eaidev-uat-session-1791980679065`), and admin mutation **9/0** (`e2eaidev-uat-admin-1791980694156`). No verified product-code bug remained open.
- Run 11 (cron live UAT sweep): stack was healthy except web :13000 was not running, so `.next` was removed and `pnpm dev` was started in a PTY session. Headed Playwright before build: v5 **37/0** (`e2eaidev-uat5-1791981920261`), ops/admin **14/0** (`e2eaidev-uat-ops-1791982038059`), session expiry **7/0** (`e2eaidev-uat-session-1791982068057`), admin mutation **9/0** (`e2eaidev-uat-admin-1791982082606`), and mobile-nav **9/0** (`e2eaidev-uat-mobile-1791982100106`). Web gate passed; after `pnpm build`, `.next` was removed, dev restarted, health endpoints returned 200, and v5 reran **37/0** (`e2eaidev-uat5-1791982226206`). Visual spot-checks: `06-chat-answer.png`, `24-id-admin.png`, and mobile `01-mobile-home-nav.png` showed the expected chat citation, Indonesian Admin page, and mobile Documents/Chat/Admin navigation.
- Run 12 (cron live UAT sweep): stack was healthy except web :13000 was not running, so `.next` was removed and `pnpm dev` was started. Headed Playwright before build: v5 **37/0** (`e2eaidev-uat5-1791983224006`), ops/admin **14/0** (`e2eaidev-uat-ops-1791983336378`), session expiry **7/0** (`e2eaidev-uat-session-1791983366261`), admin mutation **9/0** (`e2eaidev-uat-admin-1791983380919`), and mobile-nav **9/0** (`e2eaidev-uat-mobile-1791983398382`). Web gate passed; after `pnpm build`, `.next` was removed, dev restarted, health endpoints returned 200, and v5 reran **37/0** (`e2eaidev-uat5-1791983525635`). No same-run product-code bug was found.
- Run 13 (cron live UAT sweep): stack was healthy except web :13000 was not running, so `.next` was removed and `pnpm dev` was started. Headed Playwright before build: v5 **37/0** (`e2eaidev-uat5-1791984518788`), ops/admin **14/0** (`e2eaidev-uat-ops-1791984663816`), session expiry **7/0** (`e2eaidev-uat-session-1791984701576`), admin mutation **9/0** (`e2eaidev-uat-admin-1791984725133`), and mobile-nav **9/0** (`e2eaidev-uat-mobile-1791984747747`). Web gate passed; after `pnpm build`, `.next` was removed, dev restarted, health endpoints returned 200, and v5 reran **37/0** (`e2eaidev-uat5-1791985017177`). No same-run product-code bug was found.
- Run 14 (cron live UAT sweep): stack was healthy except web :13000 was not running, so `.next` was removed and `pnpm dev` was started. Headed Playwright before build: v5 **37/0** (`e2eaidev-uat5-1791986045196`), ops/admin **14/0** (`e2eaidev-uat-ops-1791986161370`), session **7/0** (`e2eaidev-uat-session-1791986197056`), admin mutation **9/0** (`e2eaidev-uat-admin-1791986218207`), and mobile-nav **9/0** (`e2eaidev-uat-mobile-1791986240229`). Web gate passed; after `pnpm build`, `.next` was removed, dev restarted, health endpoints returned 200, and v5 reran **37/0** (`e2eaidev-uat5-1791986468896`). No same-run product-code bug was found.
- Run 15 (cron live UAT sweep): stack was healthy at start: API `/health` + `/ready`, web `/`, and web proxy `/api/v1/health` all returned 200. Headed Playwright before build: v5 **37/0** (`e2eaidev-uat5-1791987529700`), ops/admin **14/0** (`e2eaidev-uat-ops-1791987646915`), session expiry **7/0** (`e2eaidev-uat-session-1791987681703`), admin mutation **9/0** (`e2eaidev-uat-admin-1791987701442`), and mobile-nav **9/0** (`e2eaidev-uat-mobile-1791987722794`). Web gate passed; after `pnpm build`, `.next` was removed, dev restarted, health endpoints returned 200, and v5 reran **37/0** (`e2eaidev-uat5-1791987854746`). No same-run product-code bug was found.
- Run 16 (cron live UAT sweep): web :13000 was down at the start while API/Docker were healthy, so `.next` was removed and `pnpm dev` was started. Headed Playwright before build: v5 **37/0** (`e2eaidev-uat5-1791988839078`), ops/admin **14/0** (`e2eaidev-uat-ops-1791988944227`), session expiry **7/0** (`e2eaidev-uat-session-1791988975672`), admin mutation **9/0** (`e2eaidev-uat-admin-1791988995355`), and mobile-nav **9/0** (`e2eaidev-uat-mobile-1791989016023`). Web gate passed; after `pnpm build`, `.next` was removed, dev restarted, health endpoints returned 200, and v5 reran **37/0** (`e2eaidev-uat5-1791989128480`). No same-run product-code bug was found.
- Scripts: `e2eaidev_uat_session.js` (session expiry), `e2eaidev_uat_ops.js` (admin Operate/Improve/Admin/upload edge cases), `e2eaidev_uat_v5.js` (current full run), `e2eaidev_uat_live.js` (happy path), `e2eaidev_uat_v2.js` (negative paths, found run-2 bugs), `e2eaidev_uat_v3.js` (run-2 regression), `e2eaidev_uat_v4.js` (run-3 Stop regression). Not yet committed as a repo suite (they need the scratch-held demo password).

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

Run 8: Quota UX (UAT-CHAT-007). Headed Chrome as Andi with temporary quota policies (script `e2eaidev_uat_quota.js`, 6 PASS / 0 FAIL): storage 413 -> "Storage quota exceeded" and no upload listed; request-rate 429 -> "Rate limit exceeded"; token budget 429 -> "Token quota exceeded". Bug found: after a failed send the question stayed as an unanswered bubble and the input was empty; now the bubble is removed and the question returned to the input. Evidence `e2eaidev-uat-quota-1791977593296` (before, `02-rate-429.png`) and `e2eaidev-uat-quota-1791978087965` (after).

Run 6: Chat citations are per answer (UAT-CHAT-006). The Citations panel shows only the newest assistant answer's citations; older assistant answers display their own citations inline, so reopened history still shows them. Component tests: new RED/GREEN for the panel and for inline history citations (20 tests in `chat-screen.test.tsx`).

Run 5: Admin login path for UAT. `e2eai-api reset-admin-password --creds-file <path>` resets or creates/migrates `admin@local.e2eai` with a random password and writes credentials to a scratch file outside the repo. No committed secret, no web backdoor; the CLI command refuses to write inside the repo tree. The headed admin UAT now covers admin login, organization snapshot, create division/team/user, add team member, and grant role. The original `admin@local` value was not browser/API-login compatible because Pydantic `EmailStr` rejects addresses without a dotted domain.

Run 4: Mobile feature navigation is now reachable below the `md` breakpoint. App shell renders a dedicated mobile feature nav for Documents / Chat / Admin above the main content while keeping the desktop sidebar at `md` and up; EN/ID landmark labels and link labels are covered by component tests and a headed 390 px Playwright UAT.

Run 3: Chat Stop is now wired to real behavior. The web client creates an `AbortController` for each send, disables Stop when nothing can be stopped, drops a late answer after an abort, calls `api.stopMessage(message_id)` when a stopped/finished assistant message id exists, and uses localized EN/ID status text.

Run 2:

API: principal validation before share; minimum-relevance floor (0.30, `retrieval.min_relevance` in e2eai.yaml); `GET /chat/conversations/{id}/messages`; `message_id` in the chat reply; stored citations keep their document; `view=trash`; `/me` returns the session csrf token.
Web: Sign out and hidden login form; "Move to Trash" label, Trash tab with Restore; chat conversation list/history/feedback; localized status text; locale persistence; sign-in hint for signed-out visitors; API reason shown on share failure.

## Verification gates (this run)

- Run 16: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health` and `/api/v1/ready` -> 200; web `/` and web proxy `/api/v1/health` -> 200 after starting `pnpm dev`. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0, mobile 9/0; after web build/restart, v5 37/0 again. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. No product-code bug was verified, so TDD/code fix and API/CLI suites were not needed.

- Run 15: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health` and `/api/v1/ready` -> 200; web `/` and web proxy `/api/v1/health` -> 200. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0, mobile 9/0; after web build/restart, v5 37/0 again. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. No product-code bug was verified, so TDD/code fix and API/CLI suites were not needed.

- Run 14: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health` and `/api/v1/ready` -> 200; web `/` and web proxy `/api/v1/health` -> 200 after starting `pnpm dev`. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0, mobile 9/0; after web build/restart, v5 37/0 again. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. No product-code bug was verified, so TDD/code fix and API/CLI suites were not needed.

- Run 13: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health` and `/api/v1/ready` -> 200; web `/` and web proxy `/api/v1/health` -> 200 after starting `pnpm dev`. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0, mobile 9/0; after web build/restart, v5 37/0 again. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. No product-code bug was verified, so TDD/code fix and API/CLI suites were not needed.

- Run 12: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health` and `/api/v1/ready` -> 200; web `/` and web proxy `/api/v1/health` -> 200 after starting `pnpm dev`. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0, mobile 9/0; after web build/restart, v5 37/0 again. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. No product-code bug was verified, so TDD/code fix and API/CLI suites were not needed.

- Run 11: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health` and `/api/v1/ready` -> 200; web `/` and web proxy `/api/v1/health` -> 200 after starting `pnpm dev`. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0, mobile 9/0; after web build/restart, v5 37/0 again. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. No product-code bug was verified, so TDD/code fix and API/CLI suites were not needed.

- Run 10: git `main` synced with `origin/main` (0/0 ahead/behind); Docker services up (postgres + valkey healthy, openfga, seaweedfs, litellm, e2eai-ollama). API `/api/v1/health`, web `/`, and web proxy `/api/v1/health` -> 200 after restarting the hung web dev server. Headed Playwright: v5 37/0, ops 14/0, session 7/0, admin 9/0. Web gate: `cd apps/web && pnpm vitest run && pnpm run typecheck && pnpm lint && pnpm run build` -> 21 files / 327 tests passed; typecheck ok; lint clean; production build ok. After build, `.next` was removed and `pnpm dev` restarted; health endpoints returned 200. No app code changed, so TDD/code fix was not needed and API/CLI suites were skipped.

- Run 8: `cd apps/web && pnpm vitest run src/components/chat-screen.test.tsx` -> RED 1 failed, GREEN 21 passed; `pnpm vitest run` -> 21 files / 322 tests passed; `pnpm run typecheck` ok; `pnpm lint` clean; `pnpm run build` ok (then `.next` wiped, dev restarted, web/proxy 200). Headed v5 -> 37/0 (baseline and after fix, `e2eaidev-uat5-1791977966868`); quota script -> 6/0. API untouched, so API suites skipped on purpose.

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

- Run 16: no new product behavior beyond the existing v5/ops/session/admin/mobile scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, admin revoke/edit flows, and screen-reader walkthrough remain out of scope.

- Run 15: no new product behavior beyond the existing v5/ops/session/admin/mobile scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, admin revoke/edit flows, and screen-reader walkthrough remain out of scope.

- Run 14: no new product behavior beyond the existing v5/ops/session/admin/mobile scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, admin revoke/edit flows, and screen-reader walkthrough remain out of scope.

- Run 13: no new product behavior beyond the existing v5/ops/session/admin/mobile scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, admin revoke/edit flows, and screen-reader walkthrough remain out of scope.

- Run 12: no new product behavior beyond the existing v5/ops/session/admin/mobile scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, admin revoke/edit flows, and screen-reader walkthrough remain out of scope.

- Run 11: no new product behavior beyond the existing v5/ops/session/admin/mobile scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, admin revoke/edit flows, and screen-reader walkthrough remain out of scope.

- Run 10: no new product behavior beyond the existing v5/ops/session/admin scripts. Drag-and-drop upload, real PDF/DOCX/Docling, production `pnpm start`, concurrent users, idle-timeout waiting for 8 hours, and admin revoke/edit flows remain out of scope.

- Run 9: session expiry covered for chat send, Documents load and re-login (cookie cleared client-side). Not covered: server-side idle expiry after `session_idle_hours` (8 h), expiry during file upload/share, other lifecycle pages (Plan/Operate/Improve) after expiry, the unexplained one-off sign-out seen in the first v5 run (cause unknown; may have been a real expiry or a session invalidated by a parallel login).

- Run 7: Admin offboarding and flywheel *triage actions* (queue was empty, so only page load was verified). Cold-start progress UI for slow first upload.

- Admin offboarding and flywheel triage actions: not exercised (empty queue). Incident report + transition (run 7) and admin org mutations (run 5) are covered.
- Drag-and-drop upload, files over quota, real PDF/DOCX (Docling not installed), screen-reader walkthrough, concurrent sessions, session idle expiry.
- Production server (`pnpm start`); UAT ran against `pnpm dev`.
- Quota 429/413 UX is covered since run 8. Not covered: countdown/Retry-After display (the UI shows only the API reason), 429 on login, and quota errors on share/search calls.
