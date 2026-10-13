# Referensi API E2EAIDEV

<!-- DIHASILKAN DARI FastAPI OpenAPI apps/api. Jangan edit manual; jalankan scripts/generate_api_reference.py. -->

Requirement: FR-F22 (referensi API P1).

Judul API: E2EAIDEV API
Versi API: 0.1.0
Total path: 158
Total operasi: 170

## Cara generate ulang

    uv --project apps/api run python scripts/generate_api_reference.py

## Autentikasi

Sebagian besar route aplikasi memerlukan sesi atau API key berscope. Referensi generated ini hanya mendokumentasikan bentuk route dan tidak pernah memuat nilai kredensial live.

## Operasi berdasarkan tag

### admin

#### GET /api/v1/admin/connector-templates

- Ringkasan: List Api
- Operation ID: `list_api_api_v1_admin_connector_templates_get`
- Kode status respons: 200

#### GET /api/v1/admin/connector-templates/{template_id}

- Ringkasan: Get Api
- Operation ID: `get_api_api_v1_admin_connector_templates__template_id__get`
- Kode status respons: 200, 422

#### POST /api/v1/admin/connector-templates/{template_id}/apply

- Ringkasan: Apply Api
- Operation ID: `apply_api_api_v1_admin_connector_templates__template_id__apply_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/model-endpoints/playground

- Ringkasan: Playground Api
- Operation ID: `playground_api_api_v1_admin_model_endpoints_playground_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/model-endpoints/register

- Ringkasan: Register Api
- Operation ID: `register_api_api_v1_admin_model_endpoints_register_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/org/divisions

- Ringkasan: Create Division Route
- Operation ID: `create_division_route_api_v1_admin_org_divisions_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/org/projects

- Ringkasan: Create Project Route
- Operation ID: `create_project_route_api_v1_admin_org_projects_post`
- Kode status respons: 200, 422

#### PATCH /api/v1/admin/org/projects/{project_id}/owner

- Ringkasan: Update Project Owner Route
- Operation ID: `update_project_owner_route_api_v1_admin_org_projects__project_id__owner_patch`
- Kode status respons: 200, 422

#### POST /api/v1/admin/org/role-grants

- Ringkasan: Grant Role Route
- Operation ID: `grant_role_route_api_v1_admin_org_role_grants_post`
- Kode status respons: 200, 422

#### GET /api/v1/admin/org/snapshot

- Ringkasan: Org Snapshot Route
- Operation ID: `org_snapshot_route_api_v1_admin_org_snapshot_get`
- Kode status respons: 200, 422

#### POST /api/v1/admin/org/team-memberships

- Ringkasan: Add Team Member Route
- Operation ID: `add_team_member_route_api_v1_admin_org_team_memberships_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/org/teams

- Ringkasan: Create Team Route
- Operation ID: `create_team_route_api_v1_admin_org_teams_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/org/users

- Ringkasan: Create User Route
- Operation ID: `create_user_route_api_v1_admin_org_users_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/systems

- Ringkasan: Register System Api
- Operation ID: `register_system_api_api_v1_admin_systems_post`
- Kode status respons: 200, 422

#### PATCH /api/v1/admin/systems/{system_id}/auth

- Ringkasan: Configure Auth Api
- Operation ID: `configure_auth_api_api_v1_admin_systems__system_id__auth_patch`
- Kode status respons: 200, 422

#### PATCH /api/v1/admin/systems/{system_id}/endpoints

- Ringkasan: Set Endpoints Api
- Operation ID: `set_endpoints_api_api_v1_admin_systems__system_id__endpoints_patch`
- Kode status respons: 200, 422

#### POST /api/v1/admin/systems/{system_id}/grants

- Ringkasan: Grant System Api
- Operation ID: `grant_system_api_api_v1_admin_systems__system_id__grants_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/systems/{system_id}/spec

- Ringkasan: Upload Spec Api
- Operation ID: `upload_spec_api_api_v1_admin_systems__system_id__spec_post`
- Kode status respons: 200, 422

#### POST /api/v1/admin/systems/{system_id}/test

- Ringkasan: Test System Api
- Operation ID: `test_system_api_api_v1_admin_systems__system_id__test_post`
- Kode status respons: 200, 422

#### POST /api/v1/users/{user_id}/deactivate

- Ringkasan: Deactivate User Api
- Operation ID: `deactivate_user_api_api_v1_users__user_id__deactivate_post`
- Kode status respons: 200, 422

### admin-config

#### GET /api/v1/admin/config/export

- Ringkasan: Export Config Api
- Operation ID: `export_config_api_api_v1_admin_config_export_get`
- Kode status respons: 200, 422

### agents

#### POST /api/v1/agents/trajectory/score

- Ringkasan: Score Trajectory Api
- Operation ID: `score_trajectory_api_api_v1_agents_trajectory_score_post`
- Kode status respons: 200, 422

#### POST /api/v1/agents/workflow/validate

- Ringkasan: Validate Workflow Api
- Operation ID: `validate_workflow_api_api_v1_agents_workflow_validate_post`
- Kode status respons: 200, 422

### api-keys

#### GET /api/v1/api-keys

- Ringkasan: List Api Keys Api
- Operation ID: `list_api_keys_api_api_v1_api_keys_get`
- Kode status respons: 200, 422

#### POST /api/v1/api-keys

- Ringkasan: Create Api Key Api
- Operation ID: `create_api_key_api_api_v1_api_keys_post`
- Kode status respons: 200, 422

#### DELETE /api/v1/api-keys/{key_id}

- Ringkasan: Revoke Api Key Api
- Operation ID: `revoke_api_key_api_api_v1_api_keys__key_id__delete`
- Kode status respons: 200, 422

### audit

#### POST /api/v1/audit/export

- Ringkasan: Export Audit Events Api
- Operation ID: `export_audit_events_api_api_v1_audit_export_post`
- Kode status respons: 200, 422

### auth

#### POST /api/v1/auth/login

- Ringkasan: Login
- Operation ID: `login_api_v1_auth_login_post`
- Kode status respons: 200, 422

#### POST /api/v1/auth/logout

- Ringkasan: Logout
- Operation ID: `logout_api_v1_auth_logout_post`
- Kode status respons: 200

#### GET /api/v1/auth/oidc/callback

- Ringkasan: Oidc Callback
- Operation ID: `oidc_callback_api_v1_auth_oidc_callback_get`
- Kode status respons: 200, 422

#### GET /api/v1/me

- Ringkasan: Me
- Operation ID: `me_api_v1_me_get`
- Kode status respons: 200

### bot-risk

#### PUT /api/v1/bots/{bot_id}/risk-classification

- Ringkasan: Classify Bot Risk Api
- Operation ID: `classify_bot_risk_api_api_v1_bots__bot_id__risk_classification_put`
- Kode status respons: 200, 422

### bots

#### POST /api/v1/bots

- Ringkasan: Create Bot Api
- Operation ID: `create_bot_api_api_v1_bots_post`
- Kode status respons: 200, 422

#### POST /api/v1/bots/{bot_id}/ask

- Ringkasan: Ask Bot Api
- Operation ID: `ask_bot_api_api_v1_bots__bot_id__ask_post`
- Kode status respons: 200, 422

#### POST /api/v1/bots/{bot_id}/bundles

- Ringkasan: Release Bundle Api
- Operation ID: `release_bundle_api_api_v1_bots__bot_id__bundles_post`
- Kode status respons: 200, 422

#### POST /api/v1/bots/{bot_id}/bundles/{bundle_id}/rollback

- Ringkasan: Rollback Bundle Api
- Operation ID: `rollback_bundle_api_api_v1_bots__bot_id__bundles__bundle_id__rollback_post`
- Kode status respons: 200, 422

#### POST /api/v1/bots/{bot_id}/environments/promote

- Ringkasan: Promote Bundle Api
- Operation ID: `promote_bundle_api_api_v1_bots__bot_id__environments_promote_post`
- Kode status respons: 200, 422

#### POST /api/v1/bots/{bot_id}/environments/release

- Ringkasan: Release To Environment Api
- Operation ID: `release_to_environment_api_api_v1_bots__bot_id__environments_release_post`
- Kode status respons: 200, 422

#### POST /api/v1/bots/{bot_id}/grants

- Ringkasan: Grant Bot Api
- Operation ID: `grant_bot_api_api_v1_bots__bot_id__grants_post`
- Kode status respons: 200, 422

#### PUT /api/v1/bots/{bot_id}/scope

- Ringkasan: Set Bot Scope Api
- Operation ID: `set_bot_scope_api_api_v1_bots__bot_id__scope_put`
- Kode status respons: 200, 422

### chat

#### POST /api/v1/chat/ask

- Ringkasan: Ask
- Operation ID: `ask_api_v1_chat_ask_post`
- Kode status respons: 200, 422

#### GET /api/v1/chat/conversations

- Ringkasan: List Conversations Api
- Operation ID: `list_conversations_api_api_v1_chat_conversations_get`
- Kode status respons: 200, 422

#### POST /api/v1/chat/conversations

- Ringkasan: Create Conversation Api
- Operation ID: `create_conversation_api_api_v1_chat_conversations_post`
- Kode status respons: 200, 422

#### PATCH /api/v1/chat/conversations/{conversation_id}

- Ringkasan: Rename Conversation Api
- Operation ID: `rename_conversation_api_api_v1_chat_conversations__conversation_id__patch`
- Kode status respons: 200, 422

#### DELETE /api/v1/chat/conversations/{conversation_id}

- Ringkasan: Delete Conversation Api
- Operation ID: `delete_conversation_api_api_v1_chat_conversations__conversation_id__delete`
- Kode status respons: 200, 422

#### POST /api/v1/chat/conversations/{conversation_id}/messages

- Ringkasan: Send Message Api
- Operation ID: `send_message_api_api_v1_chat_conversations__conversation_id__messages_post`
- Kode status respons: 200, 422

#### POST /api/v1/chat/mcp-tool-plan

- Ringkasan: Mcp Tool Plan Api
- Operation ID: `mcp_tool_plan_api_api_v1_chat_mcp_tool_plan_post`
- Kode status respons: 200, 422

#### POST /api/v1/chat/tool-calls/{tool_call_id}/confirm

- Ringkasan: Confirm Tool Call Api
- Operation ID: `confirm_tool_call_api_api_v1_chat_tool_calls__tool_call_id__confirm_post`
- Kode status respons: 200, 422

#### POST /api/v1/messages/{message_id}/feedback

- Ringkasan: Feedback Api
- Operation ID: `feedback_api_api_v1_messages__message_id__feedback_post`
- Kode status respons: 200, 422

#### POST /api/v1/messages/{message_id}/stop

- Ringkasan: Stop Api
- Operation ID: `stop_api_api_v1_messages__message_id__stop_post`
- Kode status respons: 200, 422

### connectors

#### POST /api/v1/connectors/sync

- Ringkasan: Sync Api
- Operation ID: `sync_api_api_v1_connectors_sync_post`
- Kode status respons: 200, 422

### data

#### POST /api/v1/data/table-query

- Ringkasan: Table Query Api
- Operation ID: `table_query_api_api_v1_data_table_query_post`
- Kode status respons: 200, 422

### documents

#### POST /api/v1/documents

- Ringkasan: Upload Document
- Operation ID: `upload_document_api_v1_documents_post`
- Kode status respons: 200, 422

#### GET /api/v1/documents/access-requests

- Ringkasan: List Access Requests Api
- Operation ID: `list_access_requests_api_api_v1_documents_access_requests_get`
- Kode status respons: 200, 422

#### POST /api/v1/documents/access-requests

- Ringkasan: Request Access Api
- Operation ID: `request_access_api_api_v1_documents_access_requests_post`
- Kode status respons: 200, 422

#### POST /api/v1/documents/access-requests/{request_id}/approve

- Ringkasan: Approve Access Request Api
- Operation ID: `approve_access_request_api_api_v1_documents_access_requests__request_id__approve_post`
- Kode status respons: 200, 422

#### POST /api/v1/documents/access-requests/{request_id}/deny

- Ringkasan: Deny Access Request Api
- Operation ID: `deny_access_request_api_api_v1_documents_access_requests__request_id__deny_post`
- Kode status respons: 200, 422

#### GET /api/v1/documents/reviews/due

- Ringkasan: Due Reviews Api
- Operation ID: `due_reviews_api_api_v1_documents_reviews_due_get`
- Kode status respons: 200

#### GET /api/v1/documents/search

- Ringkasan: Search Documents Api
- Operation ID: `search_documents_api_api_v1_documents_search_get`
- Kode status respons: 200, 422

#### GET /api/v1/documents/visible-chunks

- Ringkasan: Visible Chunks Api
- Operation ID: `visible_chunks_api_api_v1_documents_visible_chunks_get`
- Kode status respons: 200

#### DELETE /api/v1/documents/{document_id}

- Ringkasan: Delete Document Api
- Operation ID: `delete_document_api_api_v1_documents__document_id__delete`
- Kode status respons: 200, 422

#### PUT /api/v1/documents/{document_id}/lifecycle

- Ringkasan: Set Lifecycle Api
- Operation ID: `set_lifecycle_api_api_v1_documents__document_id__lifecycle_put`
- Kode status respons: 200, 422

#### POST /api/v1/documents/{document_id}/lifecycle/reviewed

- Ringkasan: Mark Reviewed Api
- Operation ID: `mark_reviewed_api_api_v1_documents__document_id__lifecycle_reviewed_post`
- Kode status respons: 200, 422

#### POST /api/v1/documents/{document_id}/restore

- Ringkasan: Restore Document Api
- Operation ID: `restore_document_api_api_v1_documents__document_id__restore_post`
- Kode status respons: 200, 422

#### PATCH /api/v1/documents/{document_id}/sensitivity

- Ringkasan: Set Sensitivity Api
- Operation ID: `set_sensitivity_api_api_v1_documents__document_id__sensitivity_patch`
- Kode status respons: 200, 422

#### POST /api/v1/documents/{document_id}/shares

- Ringkasan: Share Document Api
- Operation ID: `share_document_api_api_v1_documents__document_id__shares_post`
- Kode status respons: 200, 422

### evals

#### POST /api/v1/evals/benchmark

- Ringkasan: Run Benchmark Api
- Operation ID: `run_benchmark_api_api_v1_evals_benchmark_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/bias-fairness

- Ringkasan: Run Bias Fairness Api
- Operation ID: `run_bias_fairness_api_api_v1_evals_bias_fairness_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/compare

- Ringkasan: Compare Runs Api
- Operation ID: `compare_runs_api_api_v1_evals_compare_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/cost-estimate

- Ringkasan: Cost Estimate Api
- Operation ID: `cost_estimate_api_api_v1_evals_cost_estimate_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/datasets

- Ringkasan: Create Dataset Api
- Operation ID: `create_dataset_api_api_v1_evals_datasets_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/datasets/{dataset_id}/annotations

- Ringkasan: Annotate Dataset Api
- Operation ID: `annotate_dataset_api_api_v1_evals_datasets__dataset_id__annotations_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/doc-understanding

- Ringkasan: Run Doc Understanding Api
- Operation ID: `run_doc_understanding_api_api_v1_evals_doc_understanding_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/load-test

- Ringkasan: Run Load Test Api
- Operation ID: `run_load_test_api_api_v1_evals_load_test_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/load-test/k6-script

- Ringkasan: K6 Script Api
- Operation ID: `k6_script_api_api_v1_evals_load_test_k6_script_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/online

- Ringkasan: Online Eval Api
- Operation ID: `online_eval_api_api_v1_evals_online_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/retrieval-metrics

- Ringkasan: Run Retrieval Metrics Api
- Operation ID: `run_retrieval_metrics_api_api_v1_evals_retrieval_metrics_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/runs

- Ringkasan: Run Eval Api
- Operation ID: `run_eval_api_api_v1_evals_runs_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/security-red-team

- Ringkasan: Run Security Red Team Api
- Operation ID: `run_security_red_team_api_api_v1_evals_security_red_team_post`
- Kode status respons: 200, 422

#### POST /api/v1/evals/structured-output

- Ringkasan: Structured Output Validity Api
- Operation ID: `structured_output_validity_api_api_v1_evals_structured_output_post`
- Kode status respons: 200, 422

#### GET /api/v1/evals/tool-catalog

- Ringkasan: Tool Catalog Api
- Operation ID: `tool_catalog_api_api_v1_evals_tool_catalog_get`
- Kode status respons: 200

### governance

#### GET /api/v1/governance/ai-inventory

- Ringkasan: List Inventory Api
- Operation ID: `list_inventory_api_api_v1_governance_ai_inventory_get`
- Kode status respons: 200, 422

#### PUT /api/v1/governance/ai-inventory

- Ringkasan: Upsert Inventory Entry Api
- Operation ID: `upsert_inventory_entry_api_api_v1_governance_ai_inventory_put`
- Kode status respons: 200, 422

#### GET /api/v1/governance/bot-approvals

- Ringkasan: List Bot Approvals Api
- Operation ID: `list_bot_approvals_api_api_v1_governance_bot_approvals_get`
- Kode status respons: 200, 422

#### POST /api/v1/governance/bot-approvals

- Ringkasan: Request Bot Approval Api
- Operation ID: `request_bot_approval_api_api_v1_governance_bot_approvals_post`
- Kode status respons: 200, 422

#### POST /api/v1/governance/bot-approvals/{approval_id}/decisions

- Ringkasan: Decide Bot Approval Api
- Operation ID: `decide_bot_approval_api_api_v1_governance_bot_approvals__approval_id__decisions_post`
- Kode status respons: 200, 422

### improve

#### GET /api/v1/improve/flywheel

- Ringkasan: Queue Api
- Operation ID: `queue_api_api_v1_improve_flywheel_get`
- Kode status respons: 200, 422

#### POST /api/v1/improve/flywheel/collect

- Ringkasan: Collect Api
- Operation ID: `collect_api_api_v1_improve_flywheel_collect_post`
- Kode status respons: 200

#### POST /api/v1/improve/flywheel/export

- Ringkasan: Export Api
- Operation ID: `export_api_api_v1_improve_flywheel_export_post`
- Kode status respons: 200, 422

#### POST /api/v1/improve/flywheel/flag

- Ringkasan: Flag Api
- Operation ID: `flag_api_api_v1_improve_flywheel_flag_post`
- Kode status respons: 200, 422

#### POST /api/v1/improve/flywheel/{item_id}/reeval

- Ringkasan: Reeval Api
- Operation ID: `reeval_api_api_v1_improve_flywheel__item_id__reeval_post`
- Kode status respons: 200, 422

#### POST /api/v1/improve/flywheel/{item_id}/release

- Ringkasan: Release Api
- Operation ID: `release_api_api_v1_improve_flywheel__item_id__release_post`
- Kode status respons: 200, 422

#### POST /api/v1/improve/flywheel/{item_id}/triage

- Ringkasan: Triage Api
- Operation ID: `triage_api_api_v1_improve_flywheel__item_id__triage_post`
- Kode status respons: 200, 422

#### POST /api/v1/improve/top-unanswered

- Ringkasan: Top Unanswered Api
- Operation ID: `top_unanswered_api_api_v1_improve_top_unanswered_post`
- Kode status respons: 200, 422

### incidents

#### GET /api/v1/incidents

- Ringkasan: List Api
- Operation ID: `list_api_api_v1_incidents_get`
- Kode status respons: 200, 422

#### POST /api/v1/incidents

- Ringkasan: Report Api
- Operation ID: `report_api_api_v1_incidents_post`
- Kode status respons: 200, 422

#### POST /api/v1/incidents/{incident_id}/postmortem

- Ringkasan: Postmortem Api
- Operation ID: `postmortem_api_api_v1_incidents__incident_id__postmortem_post`
- Kode status respons: 200, 422

#### POST /api/v1/incidents/{incident_id}/traces

- Ringkasan: Traces Api
- Operation ID: `traces_api_api_v1_incidents__incident_id__traces_post`
- Kode status respons: 200, 422

#### POST /api/v1/incidents/{incident_id}/transition

- Ringkasan: Transition Api
- Operation ID: `transition_api_api_v1_incidents__incident_id__transition_post`
- Kode status respons: 200, 422

### learn

#### GET /api/v1/learn/paths

- Ringkasan: List Api
- Operation ID: `list_api_api_v1_learn_paths_get`
- Kode status respons: 200

#### GET /api/v1/learn/paths/{path_id}

- Ringkasan: Get Api
- Operation ID: `get_api_api_v1_learn_paths__path_id__get`
- Kode status respons: 200, 422

#### POST /api/v1/learn/paths/{path_id}/progress

- Ringkasan: Progress Api
- Operation ID: `progress_api_api_v1_learn_paths__path_id__progress_post`
- Kode status respons: 200, 422

#### GET /api/v1/learn/scenarios

- Ringkasan: List Api
- Operation ID: `list_api_api_v1_learn_scenarios_get`
- Kode status respons: 200

#### GET /api/v1/learn/scenarios/{scenario_id}

- Ringkasan: Get Api
- Operation ID: `get_api_api_v1_learn_scenarios__scenario_id__get`
- Kode status respons: 200, 422

#### POST /api/v1/learn/scenarios/{scenario_id}/check

- Ringkasan: Check Api
- Operation ID: `check_api_api_v1_learn_scenarios__scenario_id__check_post`
- Kode status respons: 200, 422

### legal-hold

#### GET /api/v1/legal-hold

- Ringkasan: List Holds Api
- Operation ID: `list_holds_api_api_v1_legal_hold_get`
- Kode status respons: 200, 422

#### PUT /api/v1/legal-hold/conversations/{conversation_id}

- Ringkasan: Set Conversation Hold Api
- Operation ID: `set_conversation_hold_api_api_v1_legal_hold_conversations__conversation_id__put`
- Kode status respons: 200, 422

#### PUT /api/v1/legal-hold/documents/{document_id}

- Ringkasan: Set Document Hold Api
- Operation ID: `set_document_hold_api_api_v1_legal_hold_documents__document_id__put`
- Kode status respons: 200, 422

#### POST /api/v1/legal-hold/retention-sweep

- Ringkasan: Retention Sweep Api
- Operation ID: `retention_sweep_api_api_v1_legal_hold_retention_sweep_post`
- Kode status respons: 200, 422

### lineage

#### GET /api/v1/lineage

- Ringkasan: Lineage Api
- Operation ID: `lineage_api_api_v1_lineage_get`
- Kode status respons: 200, 422

#### GET /api/v1/lineage/summary

- Ringkasan: Lineage Summary Api
- Operation ID: `lineage_summary_api_api_v1_lineage_summary_get`
- Kode status respons: 200

### memory

#### GET /api/v1/memory

- Ringkasan: List Api
- Operation ID: `list_api_api_v1_memory_get`
- Kode status respons: 200

#### POST /api/v1/memory

- Ringkasan: Add Api
- Operation ID: `add_api_api_v1_memory_post`
- Kode status respons: 200, 422

#### DELETE /api/v1/memory

- Ringkasan: Clear Api
- Operation ID: `clear_api_api_v1_memory_delete`
- Kode status respons: 200

#### PUT /api/v1/memory/settings

- Ringkasan: Settings Api
- Operation ID: `settings_api_api_v1_memory_settings_put`
- Kode status respons: 200, 422

#### DELETE /api/v1/memory/{memory_id}

- Ringkasan: Delete Api
- Operation ID: `delete_api_api_v1_memory__memory_id__delete`
- Kode status respons: 200, 422

### model-registry

#### GET /api/v1/model-registry

- Ringkasan: List Models Api
- Operation ID: `list_models_api_api_v1_model_registry_get`
- Kode status respons: 200, 422

#### POST /api/v1/model-registry

- Ringkasan: Register Model Api
- Operation ID: `register_model_api_api_v1_model_registry_post`
- Kode status respons: 200, 422

#### POST /api/v1/model-registry/{name}/{version}/decision

- Ringkasan: Decide Api
- Operation ID: `decide_api_api_v1_model_registry__name___version__decision_post`
- Kode status respons: 200, 422

#### POST /api/v1/model-registry/{name}/{version}/eval-runs

- Ringkasan: Attach Eval Run Api
- Operation ID: `attach_eval_run_api_api_v1_model_registry__name___version__eval_runs_post`
- Kode status respons: 200, 422

#### GET /api/v1/model-registry/{name}/{version}/lineage

- Ringkasan: Lineage Api
- Operation ID: `lineage_api_api_v1_model_registry__name___version__lineage_get`
- Kode status respons: 200, 422

### model-security

#### POST /api/v1/model-security/evaluate

- Ringkasan: Evaluate Api
- Operation ID: `evaluate_api_api_v1_model_security_evaluate_post`
- Kode status respons: 200, 422

#### POST /api/v1/model-security/scan-pickle

- Ringkasan: Scan Pickle Api
- Operation ID: `scan_pickle_api_api_v1_model_security_scan_pickle_post`
- Kode status respons: 200, 422

### models

#### POST /api/v1/models/finetune/check-data

- Ringkasan: Check Data Api
- Operation ID: `check_data_api_api_v1_models_finetune_check_data_post`
- Kode status respons: 200, 422

#### POST /api/v1/models/finetune/plan

- Ringkasan: Plan Api
- Operation ID: `plan_api_api_v1_models_finetune_plan_post`
- Kode status respons: 200, 422

#### POST /api/v1/models/finetune/results

- Ringkasan: Results Api
- Operation ID: `results_api_api_v1_models_finetune_results_post`
- Kode status respons: 200, 422

#### POST /api/v1/models/quantization/compare

- Ringkasan: Compare Api
- Operation ID: `compare_api_api_v1_models_quantization_compare_post`
- Kode status respons: 200, 422

### notifications

#### GET /api/v1/notifications

- Ringkasan: List My Notifications
- Operation ID: `list_my_notifications_api_v1_notifications_get`
- Kode status respons: 200, 422

#### POST /api/v1/notifications/incident-raised

- Ringkasan: Incident Raised Api
- Operation ID: `incident_raised_api_api_v1_notifications_incident_raised_post`
- Kode status respons: 200, 422

#### POST /api/v1/notifications/release-approved

- Ringkasan: Release Approved Api
- Operation ID: `release_approved_api_api_v1_notifications_release_approved_post`
- Kode status respons: 200, 422

#### POST /api/v1/notifications/review-assigned

- Ringkasan: Review Assigned Api
- Operation ID: `review_assigned_api_api_v1_notifications_review_assigned_post`
- Kode status respons: 200, 422

### openai-compatible

#### POST /api/v1/openai/chat/completions

- Ringkasan: Completions Api
- Operation ID: `completions_api_api_v1_openai_chat_completions_post`
- Kode status respons: 200, 422

#### GET /api/v1/openai/models

- Ringkasan: Models Api
- Operation ID: `models_api_api_v1_openai_models_get`
- Kode status respons: 200

### operate

#### POST /api/v1/operate/drift

- Ringkasan: Drift Api
- Operation ID: `drift_api_api_v1_operate_drift_post`
- Kode status respons: 200, 422

#### POST /api/v1/operate/finops-chargeback

- Ringkasan: Finops Chargeback Api
- Operation ID: `finops_chargeback_api_api_v1_operate_finops_chargeback_post`
- Kode status respons: 200, 422

#### GET /api/v1/operate/finops-dashboard

- Ringkasan: Finops Dashboard Api
- Operation ID: `finops_dashboard_api_api_v1_operate_finops_dashboard_get`
- Kode status respons: 200, 422

#### POST /api/v1/operate/finops-spend

- Ringkasan: Finops Spend Api
- Operation ID: `finops_spend_api_api_v1_operate_finops_spend_post`
- Kode status respons: 200, 422

#### GET /api/v1/operate/finops-window

- Ringkasan: Finops Window Api
- Operation ID: `finops_window_api_api_v1_operate_finops_window_get`
- Kode status respons: 200, 422

#### POST /api/v1/operate/finops-window

- Ringkasan: Finops Window Persist Api
- Operation ID: `finops_window_persist_api_api_v1_operate_finops_window_post`
- Kode status respons: 200, 422

#### POST /api/v1/operate/gpu-schedule

- Ringkasan: Gpu Schedule Api
- Operation ID: `gpu_schedule_api_api_v1_operate_gpu_schedule_post`
- Kode status respons: 200, 422

#### GET /api/v1/operate/slo-dashboard

- Ringkasan: Slo Dashboard Api
- Operation ID: `slo_dashboard_api_api_v1_operate_slo_dashboard_get`
- Kode status respons: 200, 422

#### POST /api/v1/operate/slo-metrics

- Ringkasan: Slo Metrics Api
- Operation ID: `slo_metrics_api_api_v1_operate_slo_metrics_post`
- Kode status respons: 200, 422

#### POST /api/v1/operate/slo-window

- Ringkasan: Slo Window Api
- Operation ID: `slo_window_api_api_v1_operate_slo_window_post`
- Kode status respons: 200, 422

#### POST /api/v1/operate/usage-roi

- Ringkasan: Usage Roi Api
- Operation ID: `usage_roi_api_api_v1_operate_usage_roi_post`
- Kode status respons: 200, 422

#### GET /api/v1/operate/usage-roi-dashboard

- Ringkasan: Usage Roi Dashboard Api
- Operation ID: `usage_roi_dashboard_api_api_v1_operate_usage_roi_dashboard_get`
- Kode status respons: 200, 422

### ops

#### GET /api/v1/health

- Ringkasan: Health
- Operation ID: `health_api_v1_health_get`
- Kode status respons: 200

#### GET /api/v1/metrics

- Ringkasan: Metrics Api
- Operation ID: `metrics_api_api_v1_metrics_get`
- Kode status respons: 200

#### GET /api/v1/ready

- Ringkasan: Ready
- Operation ID: `ready_api_v1_ready_get`
- Kode status respons: 200

### plan

#### POST /api/v1/plan/use-cases

- Ringkasan: Create Use Case Intake Api
- Operation ID: `create_use_case_intake_api_api_v1_plan_use_cases_post`
- Kode status respons: 200, 422

### preferences

#### GET /api/v1/me/preferences

- Ringkasan: Get Preferences
- Operation ID: `get_preferences_api_v1_me_preferences_get`
- Kode status respons: 200

#### PUT /api/v1/me/preferences/time-zone

- Ringkasan: Put Time Zone
- Operation ID: `put_time_zone_api_v1_me_preferences_time_zone_put`
- Kode status respons: 200, 422

### privacy

#### POST /api/v1/privacy/subjects/{user_id}/erase

- Ringkasan: Erase Api
- Operation ID: `erase_api_api_v1_privacy_subjects__user_id__erase_post`
- Kode status respons: 200, 422

#### GET /api/v1/privacy/subjects/{user_id}/export

- Ringkasan: Export Api
- Operation ID: `export_api_api_v1_privacy_subjects__user_id__export_get`
- Kode status respons: 200, 422

### prompts

#### POST /api/v1/prompts

- Ringkasan: Create Prompt Api
- Operation ID: `create_prompt_api_api_v1_prompts_post`
- Kode status respons: 200, 422

#### POST /api/v1/prompts/playground/preview

- Ringkasan: Prompt Preview Api
- Operation ID: `prompt_preview_api_api_v1_prompts_playground_preview_post`
- Kode status respons: 200, 422

#### POST /api/v1/prompts/{prompt_id}/diff

- Ringkasan: Diff Prompt Versions Api
- Operation ID: `diff_prompt_versions_api_api_v1_prompts__prompt_id__diff_post`
- Kode status respons: 200, 422

#### PUT /api/v1/prompts/{prompt_id}/labels

- Ringkasan: Set Prompt Label Api
- Operation ID: `set_prompt_label_api_api_v1_prompts__prompt_id__labels_put`
- Kode status respons: 200, 422

#### GET /api/v1/prompts/{prompt_id}/versions

- Ringkasan: List Prompt Versions Api
- Operation ID: `list_prompt_versions_api_api_v1_prompts__prompt_id__versions_get`
- Kode status respons: 200, 422

#### POST /api/v1/prompts/{prompt_id}/versions

- Ringkasan: Add Prompt Version Api
- Operation ID: `add_prompt_version_api_api_v1_prompts__prompt_id__versions_post`
- Kode status respons: 200, 422

### retrieval

#### POST /api/v1/retrieval/graph-expand

- Ringkasan: Graph Expand Api
- Operation ID: `graph_expand_api_api_v1_retrieval_graph_expand_post`
- Kode status respons: 200, 422

#### POST /api/v1/retrieval/route-kbs

- Ringkasan: Route Kbs Api
- Operation ID: `route_kbs_api_api_v1_retrieval_route_kbs_post`
- Kode status respons: 200, 422

### rollouts

#### POST /api/v1/rollouts/assign

- Ringkasan: Assign Api
- Operation ID: `assign_api_api_v1_rollouts_assign_post`
- Kode status respons: 200, 422

#### POST /api/v1/rollouts/promotion

- Ringkasan: Promotion Api
- Operation ID: `promotion_api_api_v1_rollouts_promotion_post`
- Kode status respons: 200, 422

### scim

#### POST /api/v1/scim/sync

- Ringkasan: Scim Sync Api
- Operation ID: `scim_sync_api_api_v1_scim_sync_post`
- Kode status respons: 200, 422

### security

#### POST /api/v1/security/api-keys/{key_id}/emergency-revoke

- Ringkasan: Emergency Revoke Api Key Api
- Operation ID: `emergency_revoke_api_key_api_api_v1_security_api_keys__key_id__emergency_revoke_post`
- Kode status respons: 200, 422

#### POST /api/v1/security/api-keys/{key_id}/rotate

- Ringkasan: Rotate Api Key Api
- Operation ID: `rotate_api_key_api_api_v1_security_api_keys__key_id__rotate_post`
- Kode status respons: 200, 422

#### POST /api/v1/security/certificate-status

- Ringkasan: Certificate Status Api
- Operation ID: `certificate_status_api_api_v1_security_certificate_status_post`
- Kode status respons: 200, 422

#### POST /api/v1/security/rotation-plan

- Ringkasan: Rotation Plan Api
- Operation ID: `rotation_plan_api_api_v1_security_rotation_plan_post`
- Kode status respons: 200, 422

### systems

#### POST /api/v1/systems/{system_id}/delegated-identity/validate

- Ringkasan: Validate Delegated Identity Api
- Operation ID: `validate_delegated_identity_api_api_v1_systems__system_id__delegated_identity_validate_post`
- Kode status respons: 200, 422

#### POST /api/v1/systems/{system_id}/mcp-descriptor

- Ringkasan: Mcp Descriptor Api
- Operation ID: `mcp_descriptor_api_api_v1_systems__system_id__mcp_descriptor_post`
- Kode status respons: 200, 422
