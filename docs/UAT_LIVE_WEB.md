# Live Web UAT — E2EAIDEV

Date: 2026-10-14 (run 2, cron)
Tester: Hermes Agent, headed Playwright / Chrome (non-headless, slowMo 60)
Target web: http://127.0.0.1:13000 · Target API: http://127.0.0.1:8000
Demo user: `andi@demo.e2eai` (not an org admin). Its local password lives only in Hermes scratch, never in the repo.

## Evidence (Hermes scratch, `C:/Users/riqan/AppData/Local/hermes/cache/scratch/`)

- Run 1 (earlier, 22/22): `e2eaidev-uat-1791957118046`
- Run 2 before fixes, v2 script: `e2eaidev-uat2-1791957806874` (**17 pass / 13 fail**; a few fails were script-order mistakes, the rest were real bugs, see UAT_BUGS.md)
- Run 2 after fixes, v3 script: `e2eaidev-uat3-1791960461338` (**36 pass / 0 fail**), screenshots `01-…24-*.png`
- Run 2 after fixes, original script: `e2eaidev-uat-1791960549558` (**22 pass / 0 fail**)
- Scripts: `e2eaidev_uat_live.js` (happy path), `e2eaidev_uat_v2.js` (negative paths, found the bugs), `e2eaidev_uat_v3.js` (same flows with fixed ordering, now the regression run). Not yet committed as a repo suite (they need the scratch-held demo password).

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
- PASS Yes/No feedback sends `POST /messages/{id}/feedback` and confirms

Locale / a11y
- PASS Indonesian choice survives full-page navigation (localStorage), `<html lang>` follows it
- PASS header status, Sign out, upload status are localized
- PASS first Tab stop is the skip link

Lifecycle pages (Plan, Data, Build, Test, Release, Operate, Improve, Admin)
- PASS all render in ID without error; a non-admin sees admin-only notices instead of dead forms
- PASS plan submit, model register, config export through the proxy (run 1)

Health
- PASS no 5xx; PASS no unexpected 4xx (expected: 401 before login, 403 admin-only, 422 invalid share); PASS no unexpected JS errors

## Fixes made from this run (all TDD, see UAT_BUGS.md)

API: principal validation before share; minimum-relevance floor (0.30, `retrieval.min_relevance` in e2eai.yaml); `GET /chat/conversations/{id}/messages`; `message_id` in the chat reply; stored citations keep their document; `view=trash`; `/me` returns the session csrf token.
Web: Sign out and hidden login form; "Move to Trash" label, Trash tab with Restore; chat conversation list/history/feedback; localized status text; locale persistence; sign-in hint for signed-out visitors; API reason shown on share failure.

## Verification gates (this run)

- API focused + adjacent: 149 passed (`test_uat_principal_and_relevance.py` 23, quotas, auth, api_keys, chat, cited answer, document lifecycle, share policy/expiry/views, search, guardrails, language, explainability, release bundle, upload ingest, semantic cache, docs, offboarding, retrieval metrics).
- Web: `pnpm vitest run` 21 files / 315 tests; `pnpm run typecheck` ok; `pnpm lint` ok; `pnpm build` ok (then `.next` wiped and dev restarted).
- `python scripts/validate_docs.py` PASS; `docs/openapi.json` + API reference regenerated, contract test passes.
- Intentionally skipped: full API suite, CLI suite, `verify-phase-0` (changes are confined to the touched modules).

## Not tested

- Admin mutations (org forms, offboarding, flywheel triage, incident report): Andi is not an admin and no admin demo login exists, so only the admin-only notices were verified.
- Chat **Stop** button: it only prints "Stopped" locally and does not call `/messages/{id}/stop` (open, UAT-CHAT-005).
- Drag-and-drop upload, files over quota, real PDF/DOCX (Docling not installed), mobile/narrow viewport (sidebar and conversation list are hidden below `md`), screen-reader walkthrough, concurrent sessions, session idle expiry.
- Production server (`pnpm start`); UAT ran against `pnpm dev`.
- Browser UX for rate-limit / token-quota 429 responses.
