"""Role-based learning paths (FR-E4).

Static, bilingual (EN/ID) ordered steps per role. Steps reference lifecycle stages, FR-E3 guided
scenarios, and docs sections. No DB: the caller supplies completed step ids and gets progress back
(unknown ids are ignored), so nothing about a learner is stored here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session
from .core.errors import AppError


def _t(en: str, id_: str) -> dict[str, str]:
    return {"en": en, "id": id_}


def _step(sid: str, stage: str, en: str, id_: str, *, scenario_id: str | None = None, doc: str | None = None) -> dict[str, Any]:
    step: dict[str, Any] = {"id": sid, "stage": stage, "title": _t(en, id_)}
    if scenario_id:
        step["scenario_id"] = scenario_id
    if doc:
        step["doc"] = doc
    return step


_PATHS: dict[str, dict[str, Any]] = {
    "ai-engineer": {
        "id": "ai-engineer", "title": _t("AI engineer", "Insinyur AI"),
        "summary": _t("Build a permission-aware RAG bot and prove it does not hallucinate.",
                      "Bangun bot RAG sadar-izin dan buktikan bot tidak berhalusinasi."),
        "steps": [
            _step("ae-data", "data", "Ingest and chunk documents", "Ingest dan chunking dokumen"),
            _step("ae-build", "build", "Build your first HR-policy bot", "Bangun bot kebijakan HR pertama", scenario_id="hr-policy-bot"),
            _step("ae-halluc", "test", "Diagnose a hallucination", "Diagnosis halusinasi", scenario_id="why-does-my-bot-hallucinate"),
            _step("ae-release", "release", "Release a bundle and roll back", "Rilis bundle dan rollback"),
        ],
    },
    "evaluator": {
        "id": "evaluator", "title": _t("Evaluator", "Evaluator"),
        "summary": _t("Design eval sets, judge answers, and catch permission leaks.",
                      "Rancang set evaluasi, nilai jawaban, dan tangkap kebocoran izin."),
        "steps": [
            _step("ev-dataset", "test", "Create and annotate a gold dataset", "Buat dan anotasi dataset gold"),
            _step("ev-leak", "test", "Find the permission leak", "Temukan kebocoran izin", scenario_id="find-the-permission-leak"),
            _step("ev-judge", "test", "Run judges and compare runs", "Jalankan judge dan bandingkan run"),
            _step("ev-online", "operate", "Review sampled online evaluation", "Tinjau evaluasi online tersampel"),
        ],
    },
    "ai-pm": {
        "id": "ai-pm", "title": _t("AI product manager", "Product manager AI"),
        "summary": _t("Scope a use case, set release gates, and read ROI.", "Tentukan use case, gerbang rilis, dan baca ROI."),
        "steps": [
            _step("pm-intake", "plan", "Write a use-case intake", "Tulis intake use case"),
            _step("pm-gates", "release", "Configure release gates and sign-off", "Atur gerbang rilis dan persetujuan"),
            _step("pm-roi", "operate", "Read usage and ROI analytics", "Baca analitik penggunaan dan ROI"),
            _step("pm-flywheel", "improve", "Triage the improvement queue", "Triase antrean perbaikan"),
        ],
    },
    "compliance": {
        "id": "compliance", "title": _t("Compliance", "Kepatuhan"),
        "summary": _t("Classify risk, review the audit trail, and handle holds and incidents.",
                      "Klasifikasi risiko, tinjau audit, dan tangani legal hold serta insiden."),
        "steps": [
            _step("co-risk", "plan", "Classify a bot's AI risk tier", "Klasifikasikan tingkat risiko AI bot"),
            _step("co-audit", "operate", "Export and review the audit log", "Ekspor dan tinjau log audit"),
            _step("co-hold", "data", "Apply a legal hold", "Terapkan legal hold"),
            _step("co-incident", "operate", "Run an AI incident to closure", "Tangani insiden AI sampai selesai"),
        ],
    },
    "platform": {
        "id": "platform", "title": _t("Platform / IT", "Platform / IT"),
        "summary": _t("Install, secure, and operate the stack.", "Instal, amankan, dan operasikan stack."),
        "steps": [
            _step("pl-install", "plan", "Run the install wizard", "Jalankan wizard instalasi"),
            _step("pl-access", "data", "Mirror permissions from a connector and SCIM", "Cerminkan izin dari konektor dan SCIM"),
            _step("pl-slo", "operate", "Set SLOs and alerts", "Atur SLO dan peringatan"),
            _step("pl-rotate", "operate", "Rotate keys and certificates", "Rotasi kunci dan sertifikat"),
        ],
    },
}


def list_paths() -> list[dict[str, Any]]:
    return [
        {"id": p["id"], "title": p["title"], "summary": p["summary"], "step_count": len(p["steps"])}
        for p in _PATHS.values()
    ]


def get_path(path_id: str) -> dict[str, Any]:
    return _PATHS[path_id]


def path_progress(path_id: str, completed_step_ids: list[str]) -> dict[str, Any]:
    steps = _PATHS[path_id]["steps"]
    valid = {s["id"] for s in steps}
    done = {x for x in completed_step_ids if x in valid}
    nxt = next((s for s in steps if s["id"] not in done), None)
    return {
        "path_id": path_id, "completed": len(done), "total": len(steps),
        "percent": round(100 * len(done) / len(steps)), "next_step": nxt,
    }


class ProgressIn(BaseModel):
    completed_step_ids: list[str] = Field(default=[], max_length=200)


router = APIRouter(prefix="/api/v1/learn/paths", tags=["learn"])


@router.get("")
async def list_api(sess: dict = Depends(current_session)) -> dict[str, Any]:
    return {"paths": list_paths()}


@router.get("/{path_id}")
async def get_api(path_id: str, sess: dict = Depends(current_session)) -> dict[str, Any]:
    try:
        return get_path(path_id)
    except KeyError as exc:
        raise AppError(404, "Learning path not found") from exc


@router.post("/{path_id}/progress")
async def progress_api(path_id: str, body: ProgressIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    try:
        return path_progress(path_id, body.completed_step_ids)
    except KeyError as exc:
        raise AppError(404, "Learning path not found") from exc
