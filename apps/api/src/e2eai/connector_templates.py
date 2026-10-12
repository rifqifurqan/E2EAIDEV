"""Ready-made connector templates for common ERP/HR/CRM systems (FR-X7).

Each template is a starter OpenAPI skeleton (no server URLs, no security schemes, no credentials), a
recommended per-user auth mode (never a service account, FR-X3), and a read-only default endpoint
selection. Paths and operation names are generic starting points that an admin must align with the
customer's real API (`verify_against_vendor_docs`), since vendor APIs differ by edition and version.
`apply_template` reuses the FR-X4 registration flow, so write operations stay off until an admin opts in.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import User, get_session
from .legal_hold import is_admin
from .system_registration import configure_auth, register_system, set_allowed_operations, upload_openapi_spec


def _param(name: str, where: str = "path", required: bool = True) -> dict[str, Any]:
    return {"name": name, "in": where, "required": required, "schema": {"type": "string"}}


def _op(op_id: str, summary: str, params: list[dict] | None = None) -> dict[str, Any]:
    return {"operationId": op_id, "summary": summary, "parameters": params or []}


def _spec(title: str, paths: dict[str, dict[str, dict]]) -> dict[str, Any]:
    return {"openapi": "3.0.3", "info": {"title": title, "version": "template-1"}, "paths": paths}


_TEMPLATES: dict[str, dict[str, Any]] = {
    "sap": {
        "id": "sap", "name": "SAP", "category": "erp", "region": "global", "auth_mode": "token_exchange",
        "description": "Purchase orders, vendors, and purchase requisitions (S/4HANA-style starting point).",
        "default_allowed_operations": ["listPurchaseOrders", "getPurchaseOrder", "getVendor"],
        "spec": _spec("SAP template", {
            "/purchase-orders": {
                "get": _op("listPurchaseOrders", "List purchase orders", [_param("status", "query", False)]),
                "post": _op("createPurchaseRequisition", "Create a purchase requisition (write)"),
            },
            "/purchase-orders/{order_id}": {"get": _op("getPurchaseOrder", "Get one purchase order", [_param("order_id")])},
            "/vendors/{vendor_id}": {"get": _op("getVendor", "Get one vendor", [_param("vendor_id")])},
        }),
    },
    "odoo": {
        "id": "odoo", "name": "Odoo", "category": "erp", "region": "global", "auth_mode": "delegated",
        "description": "Sales orders, invoices, and customers (Odoo-style starting point).",
        "default_allowed_operations": ["listSaleOrders", "getSaleOrder", "getInvoice"],
        "spec": _spec("Odoo template", {
            "/sale-orders": {
                "get": _op("listSaleOrders", "List sales orders", [_param("state", "query", False)]),
                "post": _op("createSaleOrder", "Create a sales order (write)"),
            },
            "/sale-orders/{order_id}": {"get": _op("getSaleOrder", "Get one sales order", [_param("order_id")])},
            "/invoices/{invoice_id}": {"get": _op("getInvoice", "Get one invoice", [_param("invoice_id")])},
        }),
    },
    "talenta-mekari": {
        "id": "talenta-mekari", "name": "Talenta (Mekari)", "category": "hr", "region": "id", "auth_mode": "token_exchange",
        "description": "Employee profile, leave balance, attendance, and leave requests (Indonesian HR starting point).",
        "default_allowed_operations": ["getEmployeeProfile", "getLeaveBalance", "listAttendance"],
        "spec": _spec("Talenta template", {
            "/employees/{employee_id}": {"get": _op("getEmployeeProfile", "Get an employee profile", [_param("employee_id")])},
            "/employees/{employee_id}/leave-balance": {
                "get": _op("getLeaveBalance", "Get leave balance", [_param("employee_id")]),
            },
            "/employees/{employee_id}/attendance": {
                "get": _op("listAttendance", "List attendance records", [_param("employee_id"), _param("month", "query", False)]),
            },
            "/leave-requests": {"post": _op("submitLeaveRequest", "Submit a leave request (write)")},
        }),
    },
    "salesforce": {
        "id": "salesforce", "name": "Salesforce", "category": "crm", "region": "global", "auth_mode": "token_exchange",
        "description": "Accounts, contacts, opportunities, and cases (Salesforce-style starting point).",
        "default_allowed_operations": ["getAccount", "listOpportunities", "getContact"],
        "spec": _spec("Salesforce template", {
            "/accounts/{account_id}": {"get": _op("getAccount", "Get one account", [_param("account_id")])},
            "/contacts/{contact_id}": {"get": _op("getContact", "Get one contact", [_param("contact_id")])},
            "/opportunities": {"get": _op("listOpportunities", "List opportunities", [_param("stage", "query", False)])},
            "/cases": {"post": _op("createCase", "Create a support case (write)")},
        }),
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": t["id"], "name": t["name"], "category": t["category"], "region": t["region"],
            "description": t["description"], "auth_mode": t["auth_mode"],
            "default_allowed_operations": list(t["default_allowed_operations"]),
            "operation_count": sum(len(item) for item in t["spec"]["paths"].values()),
            "verify_against_vendor_docs": True,
        }
        for t in _TEMPLATES.values()
    ]


def get_template(template_id: str) -> dict[str, Any]:
    return _TEMPLATES[template_id]


async def apply_template(session: AsyncSession, *, actor: User, template_id: str) -> dict[str, Any]:
    """Register a system from a template: spec uploaded, read-only endpoints allowed, auth mode set."""
    if actor.status != "active" or not await is_admin(session, actor):
        raise AppError(403, "Not allowed")
    tpl = _TEMPLATES.get(template_id)
    if tpl is None:
        raise AppError(404, "Template not found")
    system = await register_system(
        session, actor=actor, name=f"{tpl['name']} (template)", description=tpl["description"]
    )
    await upload_openapi_spec(session, system_id=system.id, spec=tpl["spec"])
    allowed = await set_allowed_operations(
        session, system_id=system.id, operation_ids=list(tpl["default_allowed_operations"])
    )
    await configure_auth(session, system_id=system.id, auth_mode=tpl["auth_mode"])
    await audit.record(
        session, f"user:{actor.id}", "system.template.apply", f"system:{system.id}",
        {"template_id": template_id, "allowed_count": len(allowed["allowed"])},
    )
    await session.commit()
    return {
        "system_id": system.id, "template": template_id, "auth_mode": tpl["auth_mode"],
        "allowed_operations": allowed["allowed"], "read_only_default": True,
    }


router = APIRouter(prefix="/api/v1/admin/connector-templates", tags=["admin"])


@router.get("")
async def list_api(sess: dict = Depends(current_session)) -> dict[str, Any]:
    require_scope(sess, "bots")
    return {"templates": list_templates()}


@router.get("/{template_id}")
async def get_api(template_id: str, sess: dict = Depends(current_session)) -> dict[str, Any]:
    require_scope(sess, "bots")
    try:
        return get_template(template_id)
    except KeyError as exc:
        raise AppError(404, "Template not found") from exc


@router.post("/{template_id}/apply")
async def apply_api(
    template_id: str, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    actor = await db.get(User, uuid.UUID(sess["user_id"]))
    if actor is None:
        raise AppError(401, "Not authenticated")
    out = await apply_template(db, actor=actor, template_id=template_id)
    return {**out, "system_id": str(out["system_id"])}
