"""Prompt registry with immutable versions, labels, diffs, and offline playground preview (FR-B1)."""

import re
import uuid
from difflib import unified_diff

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Prompt, PromptLabel, PromptVersion, User, get_session

_VARIABLE_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_LABELS = {"production", "staging", "draft", "testing"}


def render_prompt_preview(template: str, variables: dict[str, object]) -> str:
    """Render a prompt preview without an LLM call.

    Only simple ``{{ variable }}`` placeholders are allowed. This keeps the playground deterministic
    and prevents the prompt registry from becoming a template-execution surface.
    """
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if not _SAFE_NAME_RE.fullmatch(name):
            raise ValueError(f"Unsupported prompt variable: {name}")
        if name not in variables:
            missing.append(name)
            return match.group(0)
        return str(variables[name])

    rendered = _VARIABLE_RE.sub(replace, template)
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ValueError(f"Missing prompt variables: {names}")
    return rendered


async def create_prompt(session: AsyncSession, *, owner: User, name: str, description: str | None = None) -> Prompt:
    if not name.strip():
        raise AppError(400, "Prompt name is required")
    prompt = Prompt(owner_id=owner.id, name=name.strip(), description=description)
    session.add(prompt)
    await session.flush()
    await audit.record(session, f"user:{owner.id}", "prompt.create", f"prompt:{prompt.id}", {"name": prompt.name})
    await session.commit()
    return prompt


async def add_prompt_version(
    session: AsyncSession,
    *,
    actor: User,
    prompt_id: uuid.UUID,
    template: str,
    notes: str | None = None,
) -> PromptVersion:
    await _load_prompt(session, prompt_id)
    if not template.strip():
        raise AppError(400, "Prompt template is required")
    next_version = (await session.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.prompt_id == prompt_id))) or 0
    version = PromptVersion(
        prompt_id=prompt_id,
        version=next_version + 1,
        template=template,
        notes=notes,
        created_by=str(actor.id),
    )
    session.add(version)
    await session.flush()
    await audit.record(
        session,
        f"user:{actor.id}",
        "prompt.version.create",
        f"prompt:{prompt_id}",
        {"version": version.version},
    )
    await session.commit()
    return version


async def list_prompt_versions(session: AsyncSession, *, prompt_id: uuid.UUID) -> list[dict]:
    await _load_prompt(session, prompt_id)
    rows = (await session.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt_id).order_by(PromptVersion.version.asc())
    )).scalars().all()
    return [_version_dict(row) for row in rows]


async def set_prompt_label(
    session: AsyncSession,
    *,
    actor: User,
    prompt_id: uuid.UUID,
    label: str,
    version_id: uuid.UUID,
) -> PromptLabel:
    label = label.strip().lower()
    if label not in _ALLOWED_LABELS:
        raise AppError(400, "Invalid prompt label", f"Allowed labels: {', '.join(sorted(_ALLOWED_LABELS))}")
    await _load_prompt(session, prompt_id)
    version = await _load_version(session, prompt_id=prompt_id, version_id=version_id)
    pointer = await session.scalar(select(PromptLabel).where(PromptLabel.prompt_id == prompt_id, PromptLabel.label == label))
    if pointer is None:
        pointer = PromptLabel(prompt_id=prompt_id, label=label, version_id=version.id, updated_by=str(actor.id))
        session.add(pointer)
    else:
        pointer.version_id = version.id
        pointer.updated_by = str(actor.id)
    await session.flush()
    await audit.record(
        session,
        f"user:{actor.id}",
        "prompt.label.set",
        f"prompt:{prompt_id}",
        {"label": label, "version": version.version},
    )
    await session.commit()
    return pointer


async def diff_prompt_versions(
    session: AsyncSession,
    *,
    prompt_id: uuid.UUID,
    from_version_id: uuid.UUID,
    to_version_id: uuid.UUID,
) -> dict:
    await _load_prompt(session, prompt_id)
    before = await _load_version(session, prompt_id=prompt_id, version_id=from_version_id)
    after = await _load_version(session, prompt_id=prompt_id, version_id=to_version_id)
    diff = "\n".join(unified_diff(
        before.template.splitlines(),
        after.template.splitlines(),
        fromfile=f"v{before.version}",
        tofile=f"v{after.version}",
        lineterm="",
    ))
    return {
        "prompt_id": str(prompt_id),
        "from_version": before.version,
        "to_version": after.version,
        "unified_diff": diff,
    }


async def _load_prompt(session: AsyncSession, prompt_id: uuid.UUID) -> Prompt:
    prompt = await session.get(Prompt, prompt_id)
    if prompt is None:
        raise AppError(404, "Prompt not found")
    return prompt


async def _load_version(session: AsyncSession, *, prompt_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersion:
    version = await session.get(PromptVersion, version_id)
    if version is None or version.prompt_id != prompt_id:
        raise AppError(404, "Prompt version not found")
    return version


def _version_dict(version: PromptVersion) -> dict:
    return {
        "id": str(version.id),
        "prompt_id": str(version.prompt_id),
        "version": version.version,
        "template": version.template,
        "notes": version.notes,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class PromptIn(BaseModel):
    name: str
    description: str | None = None


class PromptVersionIn(BaseModel):
    template: str
    notes: str | None = None


class PromptLabelIn(BaseModel):
    label: str
    version_id: uuid.UUID


class PromptDiffIn(BaseModel):
    from_version_id: uuid.UUID
    to_version_id: uuid.UUID


class PromptPreviewIn(BaseModel):
    template: str
    variables: dict[str, object] = {}


router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


@router.post("")
async def create_prompt_api(body: PromptIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    prompt = await create_prompt(db, owner=user, name=body.name, description=body.description)
    return {"id": str(prompt.id), "name": prompt.name, "description": prompt.description}


@router.post("/{prompt_id}/versions")
async def add_prompt_version_api(prompt_id: uuid.UUID, body: PromptVersionIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    version = await add_prompt_version(db, actor=user, prompt_id=prompt_id, template=body.template, notes=body.notes)
    return _version_dict(version)


@router.get("/{prompt_id}/versions")
async def list_prompt_versions_api(prompt_id: uuid.UUID, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    return {"versions": await list_prompt_versions(db, prompt_id=prompt_id)}


@router.put("/{prompt_id}/labels")
async def set_prompt_label_api(prompt_id: uuid.UUID, body: PromptLabelIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    label = await set_prompt_label(db, actor=user, prompt_id=prompt_id, label=body.label, version_id=body.version_id)
    return {"label": label.label, "version_id": str(label.version_id)}


@router.post("/{prompt_id}/diff")
async def diff_prompt_versions_api(prompt_id: uuid.UUID, body: PromptDiffIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    return await diff_prompt_versions(db, prompt_id=prompt_id, from_version_id=body.from_version_id, to_version_id=body.to_version_id)


@router.post("/playground/preview")
async def prompt_preview_api(body: PromptPreviewIn, sess: dict = Depends(current_session)) -> dict:
    require_scope(sess, "bots")
    try:
        return {"rendered": render_prompt_preview(body.template, body.variables)}
    except ValueError as exc:
        raise AppError(400, "Prompt preview failed", str(exc)) from exc
