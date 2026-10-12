"""FastAPI application entrypoint for Phase 0 (PRD T1/T7)."""

from fastapi import FastAPI
from sqlalchemy import text

from .ai_inventory import router as ai_inventory_router
from .audit_export import router as audit_export_router
from .secret_rotation import router as secret_rotation_router
from .doc_lifecycle import router as doc_lifecycle_router
from .index_lineage import router as index_lineage_router
from .legal_hold import router as legal_hold_router
from .model_registry import router as model_registry_router
from .model_file_security import router as model_file_security_router
from .model_endpoints import router as model_endpoints_router
from .bias_fairness import router as bias_fairness_router
from .load_test import router as load_test_router
from .rollout import router as rollout_router
from .online_eval import router as online_eval_router
from .drift import router as drift_router
from .incidents import router as incidents_router
from .flywheel import router as flywheel_router
from .scenarios import router as scenarios_router
from .connectors import router as connectors_router
from .connector_templates import router as connector_templates_router
from .openai_compat import router as openai_compat_router
from .scim_sync import router as scim_router
from .learning_paths import router as learning_paths_router
from .table_qa import router as table_qa_router
from .agent_workflow import router as agent_workflow_router
from .quantization_lab import router as quantization_lab_router
from .finetune_plan import router as finetune_plan_router
from .gpu_scheduler import router as gpu_scheduler_router
from .advanced_rag import router as advanced_rag_router
from .auth import router as auth_router
from .benchmark import router as benchmark_router
from .bot_approval import router as bot_approval_router
from .config_export import router as config_export_router
from .doc_understanding import router as doc_understanding_router
from .bot_release import router as bot_router
from .bot_risk import router as bot_risk_router
from .chat import router as chat_router
from .documents import router as documents_router
from .eval_lab import router as evals_router
from .finops import router as finops_router
from .offboarding import router as offboarding_router
from .notifications import router as notifications_router
from .org import router as org_router
from .plan_intake import router as plan_intake_router
from .prompt_registry import router as prompt_router
from .retrieval import router as retrieval_router
from .security_red_team import router as security_red_team_router
from .slo_metrics import router as slo_metrics_router
from .top_unanswered import router as top_unanswered_router
from .usage_roi import router as usage_roi_router
from .mcp_gen import router as mcp_gen_router
from .mcp_tool_call import router as mcp_tool_call_router
from .delegated_identity import router as delegated_identity_router
from .system_registration import router as system_registration_router
from .write_confirmation import router as write_confirmation_router
from .core.errors import install
from .db import sessions


def create_app() -> FastAPI:
    app = FastAPI(title="E2EAIDEV API", version="0.1.0")
    install(app)
    app.include_router(ai_inventory_router)
    app.include_router(audit_export_router)
    app.include_router(secret_rotation_router)
    app.include_router(auth_router)
    app.include_router(bot_approval_router)
    app.include_router(bot_router)
    app.include_router(bot_risk_router)
    app.include_router(chat_router)
    app.include_router(config_export_router)
    app.include_router(doc_lifecycle_router)
    app.include_router(index_lineage_router)
    app.include_router(legal_hold_router)
    app.include_router(model_registry_router)
    app.include_router(model_file_security_router)
    app.include_router(model_endpoints_router)
    app.include_router(bias_fairness_router)
    app.include_router(load_test_router)
    app.include_router(rollout_router)
    app.include_router(online_eval_router)
    app.include_router(drift_router)
    app.include_router(incidents_router)
    app.include_router(flywheel_router)
    app.include_router(scenarios_router)
    app.include_router(connectors_router)
    app.include_router(connector_templates_router)
    app.include_router(openai_compat_router)
    app.include_router(scim_router)
    app.include_router(learning_paths_router)
    app.include_router(table_qa_router)
    app.include_router(agent_workflow_router)
    app.include_router(quantization_lab_router)
    app.include_router(finetune_plan_router)
    app.include_router(gpu_scheduler_router)
    app.include_router(advanced_rag_router)
    app.include_router(documents_router)
    app.include_router(retrieval_router)
    app.include_router(evals_router)
    app.include_router(benchmark_router)
    app.include_router(doc_understanding_router)
    app.include_router(security_red_team_router)
    app.include_router(offboarding_router)
    app.include_router(notifications_router)
    app.include_router(org_router)
    app.include_router(plan_intake_router)
    app.include_router(prompt_router)
    app.include_router(slo_metrics_router)
    app.include_router(finops_router)
    app.include_router(usage_roi_router)
    app.include_router(top_unanswered_router)
    app.include_router(mcp_gen_router)
    app.include_router(mcp_tool_call_router)
    app.include_router(delegated_identity_router)
    app.include_router(system_registration_router)
    app.include_router(write_confirmation_router)

    from .api_keys import make_router as api_keys_router
    app.include_router(api_keys_router())

    @app.get("/api/v1/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/ready", tags=["ops"])
    async def ready() -> dict[str, str]:
        async with sessions()() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
