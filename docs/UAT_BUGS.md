# UAT Bug List — E2EAIDEV Live Web

Date: 2026-10-14 12:53:06 +0700
Latest UAT evidence: `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev-uat-1791957118046`
Latest result: **22 passed / 0 failed / 0 open UAT issues**

## Fixed in this UAT cycle

### UAT-DOC-001 — Documents list disappeared after reload

Severity: High
Category: Functional
Status: Fixed
Evidence before fix: `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev-uat-1791956299265/17-documents-reload.png`
Verification after fix: `documents-persist-after-reload` PASS in `e2eaidev-uat-1791957118046/uat-results.json`

Steps reproduced:
1. Sign in as demo user.
2. Open Documents.
3. Upload `leave-policy-uat.txt`.
4. Reload `/documents`.

Expected: previously uploaded documents load from the API after reload.
Actual before fix: page returned to `No documents found.` because `DocumentsScreen` only kept upload state in memory.
Fix: added backend `GET /api/v1/documents`, client `listDocuments`, and `DocumentsScreen` backend load on mount.

### UAT-DOC-002 — Documents search was not wired to backend

Severity: Medium
Category: Functional
Status: Fixed
Evidence before fix: search input existed but had no state or API call.
Verification after fix: `documents-search-filters-list` PASS in `e2eaidev-uat-1791957118046/uat-results.json`

Steps reproduced:
1. Open Documents with an uploaded document visible.
2. Type an unmatched query in the search box.

Expected: search queries backend and updates the visible list/empty state.
Actual before fix: search box did nothing.
Fix: added client `searchDocuments(query, view)` and debounced backend search in `DocumentsScreen`.

### UAT-DOC-003 — Documents tabs only changed local styling, not backend view

Severity: Medium
Category: Functional
Status: Fixed
Evidence before fix: tabs changed aria-selected only; no API view load.
Verification after fix: `documents-shared-tab-fetches-shared-view` PASS in `e2eaidev-uat-1791957118046/uat-results.json`

Steps reproduced:
1. Open Documents.
2. Click Shared with Me / My Team.

Expected: selected tab fetches the corresponding permission-filtered backend view.
Actual before fix: tab changed visually but data remained local/in-memory.
Fix: mapped tabs to backend views `my_documents`, `shared_with_me`, and `my_team`.

### UAT-OPS-001 — Operate showed a dead incident report form to non-admin user

Severity: High
Category: Functional / UX
Status: Fixed
Evidence before fix: `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev-uat-1791956299265/12-operate-report.png`
Verification after fix: `operate-non-admin-shows-notice-without-dead-form` PASS in `e2eaidev-uat-1791957118046/uat-results.json`

Steps reproduced:
1. Sign in as demo user Andi (non-admin).
2. Open Operate.
3. Try to report an incident.

Expected: non-admin user sees an admin-only notice and no form that will fail.
Actual before fix: incident form was visible, but incident APIs returned 403.
Fix: render `ReportIncidentForm` only when incident list state is `ready`; forbidden state shows admin-only notice.

## Open UAT bugs

No open UAT bugs from the latest headed run.

## Watch list / follow-up

- Convert the scratch headed UAT script into a repo-maintained Playwright suite if recurring UAT should be one command.
- Add an admin demo user or documented admin login path if UAT needs to execute admin mutation flows, not just verify admin-only notices for non-admins.
- Production deploy target is not defined yet; local proxy/API target is valid for local development only.
