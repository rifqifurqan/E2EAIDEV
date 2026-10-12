# E2EAIDEV API Reference

<!-- GENERATED FROM apps/api FastAPI OpenAPI. Do not edit by hand; run scripts/generate_api_reference.py. -->

Requirement: FR-F22 (P1 API reference).

API title: E2EAIDEV API
API version: 0.1.0
Total paths: 148
Total operations: 158

## How to regenerate

    uv --project apps/api run python scripts/generate_api_reference.py

## Authentication

Most application routes require a scoped session or API key. This generated reference documents route shape only and never includes live credential values.

## Operations by tag

### admin

#### GET /api/v1/admin/connector-templates

- Summary: List Api
- Operation ID: `list_api_api_v1_admin_connector_templates_get`
- Response status codes: 200

#### GET /api/v1/admin/connector-templates/{template_id}

- Summary: Get Api
- Operation ID: `get_api_api_v1_admin_connector_templates__template_id__get`
- Response status codes: 200, 422

#### POST /api/v1/admin/connector-templates/{template_id}/apply

- Summary: Apply Api
- Operation ID: `apply_api_api_v1_admin_connector_templates__template_id__apply_post`
- Response status codes: 200, 422

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

### admin-config

#### GET /api/v1/admin/config/export

- Summary: Export Config Api
- Operation ID: `export_config_api_api_v1_admin_config_export_get`
- Response status codes: 200, 422

### agents

#### POST /api/v1/agents/trajectory/score

- Summary: Score Trajectory Api
- Operation ID: `score_trajectory_api_api_v1_agents_trajectory_score_post`
- Response status codes: 200, 422

#### POST /api/v1/agents/workflow/validate

- Summary: Validate Workflow Api
- Operation ID: `validate_workflow_api_api_v1_agents_workflow_validate_post`
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

### audit

#### POST /api/v1/audit/export

- Summary: Export Audit Events Api
- Operation ID: `export_audit_events_api_api_v1_audit_export_post`
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

### bot-risk

#### PUT /api/v1/bots/{bot_id}/risk-classification

- Summary: Classify Bot Risk Api
- Operation ID: `classify_bot_risk_api_api_v1_bots__bot_id__risk_classification_put`
- Response status codes: 200, 422

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

### connectors

#### POST /api/v1/connectors/sync

- Summary: Sync Api
- Operation ID: `sync_api_api_v1_connectors_sync_post`
- Response status codes: 200, 422

### data

#### POST /api/v1/data/table-query

- Summary: Table Query Api
- Operation ID: `table_query_api_api_v1_data_table_query_post`
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

#### GET /api/v1/documents/reviews/due

- Summary: Due Reviews Api
- Operation ID: `due_reviews_api_api_v1_documents_reviews_due_get`
- Response status codes: 200

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

#### PUT /api/v1/documents/{document_id}/lifecycle

- Summary: Set Lifecycle Api
- Operation ID: `set_lifecycle_api_api_v1_documents__document_id__lifecycle_put`
- Response status codes: 200, 422

#### POST /api/v1/documents/{document_id}/lifecycle/reviewed

- Summary: Mark Reviewed Api
- Operation ID: `mark_reviewed_api_api_v1_documents__document_id__lifecycle_reviewed_post`
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

#### POST /api/v1/evals/bias-fairness

- Summary: Run Bias Fairness Api
- Operation ID: `run_bias_fairness_api_api_v1_evals_bias_fairness_post`
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

#### POST /api/v1/evals/load-test

- Summary: Run Load Test Api
- Operation ID: `run_load_test_api_api_v1_evals_load_test_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/load-test/k6-script

- Summary: K6 Script Api
- Operation ID: `k6_script_api_api_v1_evals_load_test_k6_script_post`
- Response status codes: 200, 422

#### POST /api/v1/evals/online

- Summary: Online Eval Api
- Operation ID: `online_eval_api_api_v1_evals_online_post`
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

### governance

#### GET /api/v1/governance/ai-inventory

- Summary: List Inventory Api
- Operation ID: `list_inventory_api_api_v1_governance_ai_inventory_get`
- Response status codes: 200, 422

#### PUT /api/v1/governance/ai-inventory

- Summary: Upsert Inventory Entry Api
- Operation ID: `upsert_inventory_entry_api_api_v1_governance_ai_inventory_put`
- Response status codes: 200, 422

#### GET /api/v1/governance/bot-approvals

- Summary: List Bot Approvals Api
- Operation ID: `list_bot_approvals_api_api_v1_governance_bot_approvals_get`
- Response status codes: 200, 422

#### POST /api/v1/governance/bot-approvals

- Summary: Request Bot Approval Api
- Operation ID: `request_bot_approval_api_api_v1_governance_bot_approvals_post`
- Response status codes: 200, 422

#### POST /api/v1/governance/bot-approvals/{approval_id}/decisions

- Summary: Decide Bot Approval Api
- Operation ID: `decide_bot_approval_api_api_v1_governance_bot_approvals__approval_id__decisions_post`
- Response status codes: 200, 422

### improve

#### GET /api/v1/improve/flywheel

- Summary: Queue Api
- Operation ID: `queue_api_api_v1_improve_flywheel_get`
- Response status codes: 200, 422

#### POST /api/v1/improve/flywheel/collect

- Summary: Collect Api
- Operation ID: `collect_api_api_v1_improve_flywheel_collect_post`
- Response status codes: 200

#### POST /api/v1/improve/flywheel/export

- Summary: Export Api
- Operation ID: `export_api_api_v1_improve_flywheel_export_post`
- Response status codes: 200, 422

#### POST /api/v1/improve/flywheel/flag

- Summary: Flag Api
- Operation ID: `flag_api_api_v1_improve_flywheel_flag_post`
- Response status codes: 200, 422

#### POST /api/v1/improve/flywheel/{item_id}/reeval

- Summary: Reeval Api
- Operation ID: `reeval_api_api_v1_improve_flywheel__item_id__reeval_post`
- Response status codes: 200, 422

#### POST /api/v1/improve/flywheel/{item_id}/release

- Summary: Release Api
- Operation ID: `release_api_api_v1_improve_flywheel__item_id__release_post`
- Response status codes: 200, 422

#### POST /api/v1/improve/flywheel/{item_id}/triage

- Summary: Triage Api
- Operation ID: `triage_api_api_v1_improve_flywheel__item_id__triage_post`
- Response status codes: 200, 422

#### POST /api/v1/improve/top-unanswered

- Summary: Top Unanswered Api
- Operation ID: `top_unanswered_api_api_v1_improve_top_unanswered_post`
- Response status codes: 200, 422

### incidents

#### GET /api/v1/incidents

- Summary: List Api
- Operation ID: `list_api_api_v1_incidents_get`
- Response status codes: 200, 422

#### POST /api/v1/incidents

- Summary: Report Api
- Operation ID: `report_api_api_v1_incidents_post`
- Response status codes: 200, 422

#### POST /api/v1/incidents/{incident_id}/postmortem

- Summary: Postmortem Api
- Operation ID: `postmortem_api_api_v1_incidents__incident_id__postmortem_post`
- Response status codes: 200, 422

#### POST /api/v1/incidents/{incident_id}/traces

- Summary: Traces Api
- Operation ID: `traces_api_api_v1_incidents__incident_id__traces_post`
- Response status codes: 200, 422

#### POST /api/v1/incidents/{incident_id}/transition

- Summary: Transition Api
- Operation ID: `transition_api_api_v1_incidents__incident_id__transition_post`
- Response status codes: 200, 422

### learn

#### GET /api/v1/learn/paths

- Summary: List Api
- Operation ID: `list_api_api_v1_learn_paths_get`
- Response status codes: 200

#### GET /api/v1/learn/paths/{path_id}

- Summary: Get Api
- Operation ID: `get_api_api_v1_learn_paths__path_id__get`
- Response status codes: 200, 422

#### POST /api/v1/learn/paths/{path_id}/progress

- Summary: Progress Api
- Operation ID: `progress_api_api_v1_learn_paths__path_id__progress_post`
- Response status codes: 200, 422

#### GET /api/v1/learn/scenarios

- Summary: List Api
- Operation ID: `list_api_api_v1_learn_scenarios_get`
- Response status codes: 200

#### GET /api/v1/learn/scenarios/{scenario_id}

- Summary: Get Api
- Operation ID: `get_api_api_v1_learn_scenarios__scenario_id__get`
- Response status codes: 200, 422

#### POST /api/v1/learn/scenarios/{scenario_id}/check

- Summary: Check Api
- Operation ID: `check_api_api_v1_learn_scenarios__scenario_id__check_post`
- Response status codes: 200, 422

### legal-hold

#### GET /api/v1/legal-hold

- Summary: List Holds Api
- Operation ID: `list_holds_api_api_v1_legal_hold_get`
- Response status codes: 200

#### PUT /api/v1/legal-hold/conversations/{conversation_id}

- Summary: Set Conversation Hold Api
- Operation ID: `set_conversation_hold_api_api_v1_legal_hold_conversations__conversation_id__put`
- Response status codes: 200, 422

#### PUT /api/v1/legal-hold/documents/{document_id}

- Summary: Set Document Hold Api
- Operation ID: `set_document_hold_api_api_v1_legal_hold_documents__document_id__put`
- Response status codes: 200, 422

#### POST /api/v1/legal-hold/retention-sweep

- Summary: Retention Sweep Api
- Operation ID: `retention_sweep_api_api_v1_legal_hold_retention_sweep_post`
- Response status codes: 200, 422

### lineage

#### GET /api/v1/lineage

- Summary: Lineage Api
- Operation ID: `lineage_api_api_v1_lineage_get`
- Response status codes: 200, 422

#### GET /api/v1/lineage/summary

- Summary: Lineage Summary Api
- Operation ID: `lineage_summary_api_api_v1_lineage_summary_get`
- Response status codes: 200

### model-registry

#### GET /api/v1/model-registry

- Summary: List Models Api
- Operation ID: `list_models_api_api_v1_model_registry_get`
- Response status codes: 200, 422

#### POST /api/v1/model-registry

- Summary: Register Model Api
- Operation ID: `register_model_api_api_v1_model_registry_post`
- Response status codes: 200, 422

#### POST /api/v1/model-registry/{name}/{version}/decision

- Summary: Decide Api
- Operation ID: `decide_api_api_v1_model_registry__name___version__decision_post`
- Response status codes: 200, 422

#### POST /api/v1/model-registry/{name}/{version}/eval-runs

- Summary: Attach Eval Run Api
- Operation ID: `attach_eval_run_api_api_v1_model_registry__name___version__eval_runs_post`
- Response status codes: 200, 422

#### GET /api/v1/model-registry/{name}/{version}/lineage

- Summary: Lineage Api
- Operation ID: `lineage_api_api_v1_model_registry__name___version__lineage_get`
- Response status codes: 200, 422

### model-security

#### POST /api/v1/model-security/evaluate

- Summary: Evaluate Api
- Operation ID: `evaluate_api_api_v1_model_security_evaluate_post`
- Response status codes: 200, 422

#### POST /api/v1/model-security/scan-pickle

- Summary: Scan Pickle Api
- Operation ID: `scan_pickle_api_api_v1_model_security_scan_pickle_post`
- Response status codes: 200, 422

### models

#### POST /api/v1/models/finetune/check-data

- Summary: Check Data Api
- Operation ID: `check_data_api_api_v1_models_finetune_check_data_post`
- Response status codes: 200, 422

#### POST /api/v1/models/finetune/plan

- Summary: Plan Api
- Operation ID: `plan_api_api_v1_models_finetune_plan_post`
- Response status codes: 200, 422

#### POST /api/v1/models/finetune/results

- Summary: Results Api
- Operation ID: `results_api_api_v1_models_finetune_results_post`
- Response status codes: 200, 422

#### POST /api/v1/models/quantization/compare

- Summary: Compare Api
- Operation ID: `compare_api_api_v1_models_quantization_compare_post`
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

### openai-compatible

#### POST /api/v1/openai/chat/completions

- Summary: Completions Api
- Operation ID: `completions_api_api_v1_openai_chat_completions_post`
- Response status codes: 200, 422

#### GET /api/v1/openai/models

- Summary: Models Api
- Operation ID: `models_api_api_v1_openai_models_get`
- Response status codes: 200

### operate

#### POST /api/v1/operate/drift

- Summary: Drift Api
- Operation ID: `drift_api_api_v1_operate_drift_post`
- Response status codes: 200, 422

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

#### POST /api/v1/operate/gpu-schedule

- Summary: Gpu Schedule Api
- Operation ID: `gpu_schedule_api_api_v1_operate_gpu_schedule_post`
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

### plan

#### POST /api/v1/plan/use-cases

- Summary: Create Use Case Intake Api
- Operation ID: `create_use_case_intake_api_api_v1_plan_use_cases_post`
- Response status codes: 200, 422

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

### retrieval

#### POST /api/v1/retrieval/graph-expand

- Summary: Graph Expand Api
- Operation ID: `graph_expand_api_api_v1_retrieval_graph_expand_post`
- Response status codes: 200, 422

#### POST /api/v1/retrieval/route-kbs

- Summary: Route Kbs Api
- Operation ID: `route_kbs_api_api_v1_retrieval_route_kbs_post`
- Response status codes: 200, 422

### rollouts

#### POST /api/v1/rollouts/assign

- Summary: Assign Api
- Operation ID: `assign_api_api_v1_rollouts_assign_post`
- Response status codes: 200, 422

#### POST /api/v1/rollouts/promotion

- Summary: Promotion Api
- Operation ID: `promotion_api_api_v1_rollouts_promotion_post`
- Response status codes: 200, 422

### scim

#### POST /api/v1/scim/sync

- Summary: Scim Sync Api
- Operation ID: `scim_sync_api_api_v1_scim_sync_post`
- Response status codes: 200, 422

### security

#### POST /api/v1/security/api-keys/{key_id}/emergency-revoke

- Summary: Emergency Revoke Api Key Api
- Operation ID: `emergency_revoke_api_key_api_api_v1_security_api_keys__key_id__emergency_revoke_post`
- Response status codes: 200, 422

#### POST /api/v1/security/api-keys/{key_id}/rotate

- Summary: Rotate Api Key Api
- Operation ID: `rotate_api_key_api_api_v1_security_api_keys__key_id__rotate_post`
- Response status codes: 200, 422

#### POST /api/v1/security/certificate-status

- Summary: Certificate Status Api
- Operation ID: `certificate_status_api_api_v1_security_certificate_status_post`
- Response status codes: 200, 422

#### POST /api/v1/security/rotation-plan

- Summary: Rotation Plan Api
- Operation ID: `rotation_plan_api_api_v1_security_rotation_plan_post`
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
