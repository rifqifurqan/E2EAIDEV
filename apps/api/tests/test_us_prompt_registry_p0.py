"""P0 prompt registry with versions, labels, diffs, and playground preview (FR-B1).

TDD: written RED before the prompt registry implementation exists.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import Prompt, PromptLabel, PromptVersion, User, sessions
from e2eai.main import create_app
from e2eai.prompt_registry import (
    add_prompt_version,
    create_prompt,
    diff_prompt_versions,
    list_prompt_versions,
    render_prompt_preview,
    set_prompt_label,
)
from e2eai.seed import seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    for model in (PromptLabel, PromptVersion, Prompt):
        await session.execute(delete(model))
    await session.commit()


async def _owner(session):
    await seed_demo(session, password="TestPassword_123456789")
    return await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))


def test_prompt_registry_versions_labels_and_diffs_are_audited():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _owner(session)

            prompt = await create_prompt(session, owner=owner, name="Sales Answer", description="Answer with citations")
            v1 = await add_prompt_version(
                session,
                actor=owner,
                prompt_id=prompt.id,
                template="Answer the question: {{ question }}\nUse: {{ context }}",
                notes="initial",
            )
            v2 = await add_prompt_version(
                session,
                actor=owner,
                prompt_id=prompt.id,
                template="Answer in {{ language }}: {{ question }}\nUse citations from {{ context }}",
                notes="language aware",
            )
            staging = await set_prompt_label(session, actor=owner, prompt_id=prompt.id, label="staging", version_id=v2.id)
            production = await set_prompt_label(session, actor=owner, prompt_id=prompt.id, label="production", version_id=v1.id)

            versions = await list_prompt_versions(session, prompt_id=prompt.id)
            assert [row["version"] for row in versions] == [1, 2]
            assert versions[0]["template"] == v1.template
            assert staging.version_id == v2.id
            assert production.version_id == v1.id

            diff = await diff_prompt_versions(session, prompt_id=prompt.id, from_version_id=v1.id, to_version_id=v2.id)
            assert diff["prompt_id"] == str(prompt.id)
            assert diff["from_version"] == 1
            assert diff["to_version"] == 2
            assert "-Answer the question: {{ question }}" in diff["unified_diff"]
            assert "+Answer in {{ language }}: {{ question }}" in diff["unified_diff"]

    _migrate()
    asyncio.run(run())


def test_prompt_playground_preview_interpolates_variables_without_model_call():
    preview = render_prompt_preview(
        "System: answer in {{ language }}.\nQuestion: {{ question }}\nContext: {{ context }}",
        {"language": "Indonesian", "question": "Apa revenue share?", "context": "Page 4 says 30 percent."},
    )
    assert preview == "System: answer in Indonesian.\nQuestion: Apa revenue share?\nContext: Page 4 says 30 percent."


def test_prompt_playground_preview_rejects_missing_variables_and_unsafe_placeholders():
    try:
        render_prompt_preview("Hello {{ name }}", {})
    except ValueError as exc:
        assert "Missing prompt variables" in str(exc)
        assert "name" in str(exc)
    else:
        raise AssertionError("missing variable was not rejected")

    try:
        render_prompt_preview("Hello {{ name.upper() }}", {"name.upper()": "BUDI"})
    except ValueError as exc:
        assert "Unsupported prompt variable" in str(exc)
    else:
        raise AssertionError("unsafe placeholder was not rejected")


def test_prompt_labels_are_safe_named_pointers_not_mutating_versions():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _owner(session)
            prompt = await create_prompt(session, owner=owner, name="Bot Prompt")
            v1 = await add_prompt_version(session, actor=owner, prompt_id=prompt.id, template="v1 {{ question }}")
            v2 = await add_prompt_version(session, actor=owner, prompt_id=prompt.id, template="v2 {{ question }}")

            await set_prompt_label(session, actor=owner, prompt_id=prompt.id, label="production", version_id=v1.id)
            moved = await set_prompt_label(session, actor=owner, prompt_id=prompt.id, label="production", version_id=v2.id)

            labels = (await session.execute(select(PromptLabel).where(PromptLabel.prompt_id == prompt.id))).scalars().all()
            assert len(labels) == 1
            assert moved.version_id == v2.id
            assert (await session.get(PromptVersion, v1.id)).template == "v1 {{ question }}"
            assert (await session.get(PromptVersion, v2.id)).template == "v2 {{ question }}"

    _migrate()
    asyncio.run(run())


def test_prompt_registry_routes_are_registered_under_api_v1():
    routes = set()
    for route in create_app().routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            routes.update(getattr(child, "path", "") for child in original.routes)
        else:
            routes.add(getattr(route, "path", ""))
    assert "/api/v1/prompts" in routes
    assert "/api/v1/prompts/{prompt_id}/versions" in routes
    assert "/api/v1/prompts/{prompt_id}/labels" in routes
    assert "/api/v1/prompts/{prompt_id}/diff" in routes
    assert "/api/v1/prompts/playground/preview" in routes
