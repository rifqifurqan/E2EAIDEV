# E2EAIDEV API Reference

<!-- GENERATED FROM apps/api FastAPI OpenAPI. Do not edit by hand; run scripts/generate_api_reference.py. -->

Requirement: FR-F22 (P1 API reference).

API title: E2EAIDEV API
API version: 0.1.0
Total paths: 81
Total operations: 87

## How to regenerate

    uv --project apps/api run python scripts/generate_api_reference.py

## Authentication

Most application routes require a scoped session or API key. This generated reference documents route shape only and never includes live credential values.

## Operations by tag

### admin

#### POST /api/v1/admin/org/divisions

- Summary: Create Division Route
- Operation ID: `create_division_route_api_v1_admin_org_divisions_post`
- Response status codes: 200, 422

#### POST /api/v1/admin/org/projects

- Summary: Create Project Route
- Operation ID: `create_project_route_api_v1_admin_org_projects_post`
- Response status codes: 200, 422

#### PATCH /api/v1/admin/org/projects/{project_id}/owner

- Summary: Update Project Owner Route
- Operation ID: `update_project_owner_route_api_v1_admin_org_projects__project_id__owner_patch`
- Response status codes: 200, 422

#### POST /api/v1/admin/org/role-grants

- Summary: Grant Role Route
- Operation ID: `grant_role_route_api_v1_admin_org_role_grants_post`
- Response status codes: 200, 422

#### GET /api/v1/admin/org/snapshot

- Summary: Org Snapshot Route
- Operation ID: `org_snapshot_route_api_v1_admin_org_snapshot_get`
- Response status codes: 200, 422

#### POST /api/v1/admin/org/team-memberships

- Summary: Add Team Member Route
- Operation ID: `add_team_member_route_api_v1_admin_org_team_memberships_post`
- Response status codes: 200, 422

#### POST /api/v1/admin/org/teams

- Summary: Create Team Route
- Operation ID: `create_team_route_api_v1_admin_org_teams_post`
- Response status codes: 200, 422

#### POST /api/v1/admin/org/users

- Summary: Create User Route
- Operation ID: `create_user_route_api_v1_admin_org_users_post`
- Response status codes: 200, 422

#### POST /api/v1/admin/systems

- Summary: Register System Api
- Operation ID: `register_system_api_api_v1_admin_systems_post`
- Response status codes: 200, 422

#### PATCH /api/v1/admin/systems/{system_id}/auth

- Summary: Configure Auth Api
- Operation ID: `configure_auth_api_api_v1_admin_systems__system_id__auth_patch`
- Response status codes: 200, 422

#### PATCH /api/v1/admin/systems/{system_id}/endpoints

- Summary: Set Endpoints Api
- Operation ID: `set_endpoints_api_api_v1_admin_systems__system_id__endpoints_patch`
- Response status codes: 200, 422

#### POST /api/v1/admin/systems/{system_id}/grants

- Summary: Grant System Api
- Operation ID: `grant_system_api_api_v1_admin_systems__system_id__grants_post`
- Response status codes: 200, 422

#### POST /api/v1/admin/systems/{system_id}/spec

- Summary: Upload Spec Api
- Operation ID: `upload_spec_api_api_v1_admin_systems__system_id__spec_post`
- Response status codes: 200, 422

#### POST /api/v1/admin/systems/{system_id}/test

- Summary: Test System Api
- Operation ID: `test_system_api_api_v1_admin_systems__system_id__test_post`
- Response status codes: 200, 422

#### POST /api/v1/users/{user_id}/deactivate

- Summary: Deactivate User Api
- Operation ID: `deactivate_user_api_api_v1_users__user_id__deactivate_post`
- Response status codes: 200, 422

### api-keys

#### GET /api/v1/api-keys

- Summary: List Api Keys Api
- Operation ID: `list_api_keys_api_api_v1_api_keys_get`
- Response status codes: 200

#### POST /api/v1/api-keys

- Summary: Create Api Key Api
- Operation ID: `create_api_key_api_api_v1_api_keys_post`
- Response status codes: 200, 422

#### DELETE /api/v1/api-keys/{key_id}

- Summary: Revoke Api Key Api
- Operation ID: `revoke_api_key_api_api_v1_api_keys__key_id__delete`
- Response status codes: 200, 422

### auth

#### POST /api/v1/auth/login

- Summary: Login
- Operation ID: `login_api_v1_auth_login_post`
- Response status codes: 200, 422

#### POST /api/v1/auth/logout

- Summary: Logout
- Operation ID: `logout_api_v1_auth_logout_post`
- Response status codes: 200

#### GET /api/v1/auth/oidc/callback

- Summary: Oidc Callback
- Operation ID: `oidc_callback_api_v1_auth_oidc_callback_get`
- Response status codes: 200, 422

#### GET /api/v1/me

- Summary: Me
- Operation ID: `me_api_v1_me_get`
- Response status codes: 200

### bots

#### POST /api/v1/bots

- Summary: Create Bot Api
- Operation ID: `create_bot_api_api_v1_bots_post`
- Response status codes: 200, 422

#### POST /api/v1/bots/{bot_id}/ask

- Summary: Ask Bot Api
- Operation ID: `ask_bot_api_api_v1_bots__bot_id__ask_post`
- Response status codes: 200, 422

#### POST /api/v1/bots/{bot_id}/bundles

- Summary: Release Bundle Api
- Operation ID: `release_bundle_api_api_v1_bots__bot_id__bundles_post`
- Response status codes: 200, 422

#### POST /api/v1/bots/{bot_id}/bundles/{bundle_id}/rollback

- Summary: Rollback Bundle Api
- Operation ID: `rollback_bundle_api_api_v1_bots__bot_id__bundles__bundle_id__rollback_post`
- Response status codes: 200, 422

#### POST /api/v1/bots/{bot_id}/environments/promote

- Summary: Promote Bundle Api
- Operation ID: `promote_bundle_api_api_v1_bots__bot_id__environments_promote_post`
- Response status codes: 200, 422

#### POST /api/v1/bots/{bot_id}/environments/release

- Summary: Release To Environment Api
- Operation ID: `release_to_environment_api_api_v1_bots__bot_id__environments_release_post`
- Response status codes: 200, 422

#### POST /api/v1/bots/{bot_id}/grants

- Summary: Grant Bot Api
- Operation ID: `grant_bot_api_api_v1_bots__bot_id__grants_post`
- Response status codes: 200, 422

#### PUT /api/v1/bots/{bot_id}/scope

- Summary: Set Bot Scope Api
- Operation ID: `set_bot_scope_api_api_v1_bots__bot_id__scope_put`
- Response status codes: 200, 422

### chat

#### POST /api/v1/chat/ask

- Summary: Ask
- Operation ID: `ask_api_v1_chat_ask_post`
- Response status codes: 200, 422

#### GET /api/v1/chat/conversations

- Summary: List Conversations Api
- Operation ID: `list_conversations_api_api_v1_chat_conversations_get`
- Response status codes: 200, 422

#### POST /api/v1/chat/conversations

- Summary: Create Conversation Api
- Operation ID: `create_conversation_api_api_v1_chat_conversations_post`
- Response status codes: 200, 422

#### PATCH /api/v1/chat/conversations/{conversation_id}

- Summary: Rename Conversation Api
- Operation ID: `rename_conversation_api_api_v1_chat_conversations__conversation_id__patch`
- Response status codes: 200, 422

#### DELETE /api/v1/chat/conversations/{conversation_id}

- Summary: Delete Conversation Api
- Operation ID: `delete_conversation_api_api_v1_chat_conversations__conversation_id__delete`
- Response status codes: 200, 422

#### POST /api/v1/chat/conversations/{conversation_id}/messages

- Summary: Send Message Api
- Operation ID: `send_message_api_api_v1_chat_conversations__conversation_id__messages_post`
- Response status codes: 200, 422

#### POST /api/v1/chat/mcp-tool-plan

- Summary: Mcp Tool Plan Api
- Operation ID: `mcp_tool_plan_api_api_v1_chat_mcp_tool_plan_post`
- Response status codes: 200, 422

#### POST /api/v1/chat/tool-calls/{tool_call_id}/confirm

- Summary: Confirm Tool Call Api
- Operation ID: `confirm_tool_call_api_api_v1_chat_tool_calls__tool_call_id__confirm_post`
- Response status codes: 200, 422

#### POST /api/v1/messages/{message_id}/feedback

- Summary: Feedback Api
- Operation ID: `feedback_api_api_v1_messages__message_id__feedback_post`
- Response status codes: 200, 422

#### POST /api/v1/messages/{message_id}/stop

- Summary: Stop Api
- Operation ID: `stop_api_api_v1_messages__message_id__stop_post`
- Response status codes: 200, 422

### documents

#### POST /api/v1/documents

- Summary: Upload Document
- Operation ID: `upload_document_api_v1_documents_post`
- Response status codes: 200, 422

#### GET /api/v1/documents/access-requests

- Summary: List Access Requests Api
- Operation ID: `list_access_requests_api_api_v1_documents_access_requests_get`
- Response status codes: 200, 422

#### POST /api/v1/documents/access-requests

- Summary: Request Access Api
- Operation ID: `request_access_api_api_v1_documents_access_requests_post`
- Response status codes: 200, 422

#### POST /api/v1/documents/access-requests/{request_id}/approve

- Summary: Approve Access Request Api
- Operation ID: `approve_access_request_api_api_v1_documents_access_requests__request_id__approve_post`
- Response status codes: 200, 422

#### POST /api/v1/documents/access-requests/{request_id}/deny

- Summary: Deny Access Request Api
- Operation ID: `deny_access_request_api_api_v1_documents_access_requests__request_id__deny_post`
- Response status codes: 200, 422

#### GET /api/v1/documents/search

- Summary: Search Documents Api
- Operation ID: `search_documents_api_api_v1_documents_search_get`
- Response status codes: 200, 422

#### GET /api/v1/documents/visible-chunks

- Summary: Visible Chunks Api
- Operation ID: `visible_chunks_api_api_v1_documents_visible_chunks_get`
- Response status codes: 200

#### DELETE /api/v1/documents/{document_id}

- Summary: Delete Document Api
- Operation ID: `delete_document_api_api_v1_documents__document_id__delete`
- Response status codes: 200, 422

#### POST /api/v1/documents/{document_id}/restore

- Summary: Restore Document Api
- Operation ID: `restore_document_api_api_v1_documents__document_id__restore_post`
- Response status codes: 200, 422

#### PATCH /api/v1/documents/{document_id}/sensitivity

- Summary: Set Sensitivity Api
- Operation ID: `set_sensitivity_api_api_v1_documents__document_id__sensitivity_patch`
- Response status codes: 200, 422

#### POST /api/v1/documents/{document_id}/shares

- Summary: Share Document Api
- Operation ID: `share_document_api_api_v1_documents__document_id__shares_post`
- Response status codes: 200, 422

### evals

#### POST /api/v1/evals/benchmark

- Summary: Run Benchmark Api
- Operation ID: `run_benchmark_api_api_v1_evals_benchmark_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/compare

- Summary: Compare Runs Api
- Operation ID: `compare_runs_api_api_v1_evals_compare_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/cost-estimate

- Summary: Cost Estimate Api
- Operation ID: `cost_estimate_api_api_v1_evals_cost_estimate_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/datasets

- Summary: Create Dataset Api
- Operation ID: `create_dataset_api_api_v1_evals_datasets_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/datasets/{dataset_id}/annotations

- Summary: Annotate Dataset Api
- Operation ID: `annotate_dataset_api_api_v1_evals_datasets__dataset_id__annotations_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/doc-understanding

- Summary: Run Doc Understanding Api
- Operation ID: `run_doc_understanding_api_api_v1_evals_doc_understanding_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/retrieval-metrics

- Summary: Run Retrieval Metrics Api
- Operation ID: `run_retrieval_metrics_api_api_v1_evals_retrieval_metrics_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/runs

- Summary: Run Eval Api
- Operation ID: `run_eval_api_api_v1_evals_runs_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/security-red-team

- Summary: Run Security Red Team Api
- Operation ID: `run_security_red_team_api_api_v1_evals_security_red_team_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/structured-output

- Summary: Structured Output Validity Api
- Operation ID: `structured_output_validity_api_api_v1_evals_structured_output_post`
- Response status codes: 200, 422

#### GET /api/v1/evals/tool-catalog

- Summary: Tool Catalog Api
- Operation ID: `tool_catalog_api_api_v1_evals_tool_catalog_get`
- Response status codes: 200

### improve

#### POST /api/v1/improve/top-unanswered

- Summary: Top Unanswered Api
- Operation ID: `top_unanswered_api_api_v1_improve_top_unanswered_post`
- Response status codes: 200, 422

### notifications

#### GET /api/v1/notifications

- Summary: List My Notifications
- Operation ID: `list_my_notifications_api_v1_notifications_get`
- Response status codes: 200, 422

#### POST /api/v1/notifications/incident-raised

- Summary: Incident Raised Api
- Operation ID: `incident_raised_api_api_v1_notifications_incident_raised_post`
- Response status codes: 200, 422

#### POST /api/v1/notifications/release-approved

- Summary: Release Approved Api
- Operation ID: `release_approved_api_api_v1_notifications_release_approved_post`
- Response status codes: 200, 422

#### POST /api/v1/notifications/review-assigned

- Summary: Review Assigned Api
- Operation ID: `review_assigned_api_api_v1_notifications_review_assigned_post`
- Response status codes: 200, 422

### operate

#### POST /api/v1/operate/finops-chargeback

- Summary: Finops Chargeback Api
- Operation ID: `finops_chargeback_api_api_v1_operate_finops_chargeback_post`
- Response status codes: 200, 422

#### GET /api/v1/operate/finops-dashboard

- Summary: Finops Dashboard Api
- Operation ID: `finops_dashboard_api_api_v1_operate_finops_dashboard_get`
- Response status codes: 200, 422

#### POST /api/v1/operate/finops-spend

- Summary: Finops Spend Api
- Operation ID: `finops_spend_api_api_v1_operate_finops_spend_post`
- Response status codes: 200, 422

#### GET /api/v1/operate/finops-window

- Summary: Finops Window Api
- Operation ID: `finops_window_api_api_v1_operate_finops_window_get`
- Response status codes: 200, 422

#### POST /api/v1/operate/finops-window

- Summary: Finops Window Persist Api
- Operation ID: `finops_window_persist_api_api_v1_operate_finops_window_post`
- Response status codes: 200, 422

#### GET /api/v1/operate/slo-dashboard

- Summary: Slo Dashboard Api
- Operation ID: `slo_dashboard_api_api_v1_operate_slo_dashboard_get`
- Response status codes: 200, 422

#### POST /api/v1/operate/slo-metrics

- Summary: Slo Metrics Api
- Operation ID: `slo_metrics_api_api_v1_operate_slo_metrics_post`
- Response status codes: 200, 422

#### POST /api/v1/operate/slo-window

- Summary: Slo Window Api
- Operation ID: `slo_window_api_api_v1_operate_slo_window_post`
- Response status codes: 200, 422

#### POST /api/v1/operate/usage-roi

- Summary: Usage Roi Api
- Operation ID: `usage_roi_api_api_v1_operate_usage_roi_post`
- Response status codes: 200, 422

#### GET /api/v1/operate/usage-roi-dashboard

- Summary: Usage Roi Dashboard Api
- Operation ID: `usage_roi_dashboard_api_api_v1_operate_usage_roi_dashboard_get`
- Response status codes: 200, 422

### ops

#### GET /api/v1/health

- Summary: Health
- Operation ID: `health_api_v1_health_get`
- Response status codes: 200

#### GET /api/v1/ready

- Summary: Ready
- Operation ID: `ready_api_v1_ready_get`
- Response status codes: 200

### prompts

#### POST /api/v1/prompts

- Summary: Create Prompt Api
- Operation ID: `create_prompt_api_api_v1_prompts_post`
- Response status codes: 200, 422

#### POST /api/v1/prompts/playground/preview

- Summary: Prompt Preview Api
- Operation ID: `prompt_preview_api_api_v1_prompts_playground_preview_post`
- Response status codes: 200, 422

#### POST /api/v1/prompts/{prompt_id}/diff

- Summary: Diff Prompt Versions Api
- Operation ID: `diff_prompt_versions_api_api_v1_prompts__prompt_id__diff_post`
- Response status codes: 200, 422

#### PUT /api/v1/prompts/{prompt_id}/labels

- Summary: Set Prompt Label Api
- Operation ID: `set_prompt_label_api_api_v1_prompts__prompt_id__labels_put`
- Response status codes: 200, 422

#### GET /api/v1/prompts/{prompt_id}/versions

- Summary: List Prompt Versions Api
- Operation ID: `list_prompt_versions_api_api_v1_prompts__prompt_id__versions_get`
- Response status codes: 200, 422

#### POST /api/v1/prompts/{prompt_id}/versions

- Summary: Add Prompt Version Api
- Operation ID: `add_prompt_version_api_api_v1_prompts__prompt_id__versions_post`
- Response status codes: 200, 422

### systems

#### POST /api/v1/systems/{system_id}/delegated-identity/validate

- Summary: Validate Delegated Identity Api
- Operation ID: `validate_delegated_identity_api_api_v1_systems__system_id__delegated_identity_validate_post`
- Response status codes: 200, 422

#### POST /api/v1/systems/{system_id}/mcp-descriptor

- Summary: Mcp Descriptor Api
- Operation ID: `mcp_descriptor_api_api_v1_systems__system_id__mcp_descriptor_post`
- Response status codes: 200, 422
