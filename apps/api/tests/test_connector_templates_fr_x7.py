"""FR-X7 ready-made connector templates (SAP, Odoo, Talenta/Mekari, Salesforce).

Deterministic/offline. A template is a starter OpenAPI skeleton (no server URLs, no security schemes,
no credentials) plus a recommended auth mode and a read-only default endpoint selection. Applying a
template uses the FR-X4 registration flow, so everything stays read-only until an admin opts in.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_catalog_lists_the_four_systems_with_safe_specs():
    from e2eai.connector_templates import get_template, list_templates
    from e2eai.mcp_gen import build_mcp_server_descriptor, validate_openapi_spec

    ids = {t["id"] for t in list_templates()}
    assert {"sap", "odoo", "talenta-mekari", "salesforce"} <= ids
    for summary in list_templates():
        assert "spec" not in summary and summary["category"] in {"erp", "hr", "crm"}
        assert summary["verify_against_vendor_docs"] is True
        tpl = get_template(summary["id"])
        spec = tpl["spec"]
        assert validate_openapi_spec(spec) == []
        text = str(spec).lower()
        assert "servers" not in spec and "securityschemes" not in text and "http://" not in text and "https://" not in text
        assert tpl["auth_mode"] in {"delegated", "token_exchange", "oauth2_cc"}
        desc = build_mcp_server_descriptor("t", spec)
        by_op = {t.operation_id: t for t in desc.tools}
        assert tpl["default_allowed_operations"] and set(tpl["default_allowed_operations"]) <= set(by_op)
        assert all(by_op[op].read_only for op in tpl["default_allowed_operations"])  # read-only by default
    with pytest.raises(KeyError):
        get_template("nope")


def test_user_data_templates_never_default_to_a_service_account_mode():
    from e2eai.connector_templates import get_template, list_templates

    for s in list_templates():
        assert get_template(s["id"])["auth_mode"] in {"delegated", "token_exchange"}  # FR-X3


def test_apply_template_registers_system_read_only_and_audited():
    async def run():
        from e2eai.connector_templates import apply_template
        from e2eai.db import AuditEntry, User, sessions
        from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo
        from e2eai.system_registration import SystemRegistration

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action == "system.template.apply"))
            await session.execute(delete(SystemRegistration).where(SystemRegistration.name == "Odoo (template)"))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            await bootstrap_admin(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))

            with pytest.raises(AppError) as exc:
                await apply_template(session, actor=andi, template_id="odoo")
            assert exc.value.status == 403
            with pytest.raises(AppError) as exc:
                await apply_template(session, actor=admin, template_id="nope")
            assert exc.value.status == 404

            out = await apply_template(session, actor=admin, template_id="odoo")
            sys_reg = await session.get(SystemRegistration, out["system_id"])
            assert sys_reg.name == "Odoo (template)" and sys_reg.status == "auth_configured"
            assert sys_reg.allowed_operations == out["allowed_operations"] and out["allowed_operations"]
            assert sys_reg.auth_config["auth_mode"] in {"delegated", "token_exchange"}
            assert "template" in out and "spec" not in str(out)
            audit = await session.scalar(select(AuditEntry).where(AuditEntry.action == "system.template.apply"))
            assert audit is not None and set(audit.details) <= {"template_id", "allowed_count"}

    _migrate()
    asyncio.run(run())


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/admin/connector-templates"]
    assert "get" in paths["/api/v1/admin/connector-templates/{template_id}"]
    assert "post" in paths["/api/v1/admin/connector-templates/{template_id}/apply"]
