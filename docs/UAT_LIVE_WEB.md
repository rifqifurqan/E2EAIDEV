# Live Web UAT — E2EAIDEV

Date: 2026-10-14 12:53:06 +0700
Tester: Hermes Agent, headed Playwright / Chrome
Target web: http://127.0.0.1:13000
Target API: http://127.0.0.1:8000
Evidence directory: `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev-uat-1791957118046`
Result JSON: `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev-uat-1791957118046/uat-results.json`

## Result

Final headed UAT result: **22 passed / 0 failed / 0 open UAT issues**.

## Prerequisites verified

- API health: `http://127.0.0.1:8000/api/v1/health` returned 200.
- Web app: `http://127.0.0.1:13000/` returned 200.
- Web-origin API proxy: `http://127.0.0.1:13000/api/v1/health` returned 200.
- Required local stack containers were running, including Postgres, Valkey, OpenFGA, SeaweedFS, LiteLLM, and `e2eai-ollama-1`.

## UAT pass matrix

- PASS `hydration-signin-button-has-react-handler` — login button is hydrated with React handler.
- PASS `login-visible-signed-in` — demo user can sign in and visible signed-in status appears.
- PASS `session-api-me-works` — `/api/v1/me` returns the signed-in user.
- PASS `session-restored-after-reload` — page reload keeps signed-in state.
- PASS `plan-use-case-form-visible` — Plan use-case intake form is visible.
- PASS `plan-use-case-submit` — Plan use-case submission returns visible created status.
- PASS `data-page-loads-real-state` — Data page renders due-review/empty state from the backend.
- PASS `build-register-model` — Build model registration creates and shows the registered model.
- PASS `test-page-loads-eval-ui` — Test/Eval page renders eval UI/state.
- PASS `release-page-loads-release-ui` — Release page renders release/bundle UI/state.
- PASS `operate-non-admin-shows-notice-without-dead-form` — demo non-admin sees admin-only notice and no dead incident form.
- PASS `improve-page-loads-flywheel-ui` — Improve page renders flywheel/admin-only state.
- PASS `documents-upload-visible` — Documents upload completes and shows the uploaded file.
- PASS `documents-share-valid-user` — Documents share succeeds with a valid user principal.
- PASS `documents-persist-after-reload` — Uploaded document list persists after page reload via backend list endpoint.
- PASS `documents-search-filters-list` — Documents search queries backend and filters results.
- PASS `documents-shared-tab-fetches-shared-view` — Documents tabs switch backend-backed views and show a clear empty/shared state.
- PASS `chat-answer-cites-uploaded-doc` — Chat answers from the uploaded document and cites it.
- PASS `admin-page-loads-or-shows-admin-notice` — Admin page renders useful admin controls/notices.
- PASS `admin-config-export-non404` — admin config export works through the web-origin proxy.
- PASS `no-unexpected-api-errors` — no unexpected API 4xx/5xx/failed requests after excluding expected auth/admin-only responses.
- PASS `no-page-js-errors` — no unexpected JavaScript/page errors after excluding expected dev/HMR and auth/admin-only noise.

## Test account and scope

The UAT used the local demo account `andi@demo.e2eai`. Its local password was reset in the Hermes scratch area for audit only and is not stored in the repository or this document.

This account is not an organization admin. Admin-only flows were validated as a real non-admin user: the UI must show admin-only messaging and must not expose dead controls that call endpoints guaranteed to return 403.

## Fixes made from this UAT

- Added `GET /api/v1/documents` to expose permission-filtered document metadata for the web document library.
- Added web API client methods `listDocuments(view)` and `searchDocuments(query, view)`.
- Reworked `DocumentsScreen` to load documents from the backend on mount, on tab changes, and on search input; uploaded documents now remain visible after reload.
- Reworked `OperateScreen` so the incident report form is only shown when incident list access is allowed; non-admin users now see a clear admin-only notice instead of a dead form.

## Not tested / remaining limits

- Admin mutation flows that require an admin user were not executed with demo user Andi. They were treated as admin-only and expected to show notices for non-admins.
- Production deployment was not tested; this UAT targets the local Docker/Compose + local Next dev server setup.
- The headed UAT script lives in Hermes scratch (`e2eaidev_uat_live.js`) and is not yet a committed reusable Playwright suite.
