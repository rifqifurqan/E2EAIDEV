"""NFR-10: erasing a person also removes flywheel items derived from their answers (not just their chats)."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select, update


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_erase_removes_flywheel_items_linked_to_the_subjects_messages_only():
    async def run():
        from e2eai.chat import create_conversation
        from e2eai.data_subject import erase_subject_data
        from e2eai.db import (
            AuditEntry, Conversation, Document, FlywheelItem, Message, MessageFeedback, User, sessions,
        )
        from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

        async with sessions()() as session:
            await session.execute(update(Conversation).values(legal_hold=False))
            await session.execute(update(Document).values(legal_hold=False))
            await session.execute(delete(FlywheelItem))
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("dsr.%")))
            await session.commit()
            erased = await session.scalar(select(User).where(User.email.like("erased-%@erased.invalid")).limit(1))
            if erased is not None:
                erased.email, erased.display_name = "andi@demo.e2eai", "Andi"
                await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            await bootstrap_admin(session, password="TestPassword_123456789")
            q = lambda e: select(User).where(func.lower(User.email) == e)  # noqa: E731
            admin = await session.scalar(q(ADMIN_EMAIL))
            andi = await session.scalar(q("andi@demo.e2eai"))
            budi = await session.scalar(q("budi@demo.e2eai"))
            admin.status = budi.status = "active"
            andi.status = "disabled"
            await session.commit()

            ids = {}
            for name, user in (("andi", andi), ("budi", budi)):
                conv = await create_conversation(session, user=user, title=f"{name} chat")
                session.add(Message(conversation_id=conv.id, role="user", content=f"{name} question"))
                await session.flush()
                answer = Message(conversation_id=conv.id, role="assistant", content=f"{name} answer")
                session.add(answer)
                await session.flush()
                session.add(MessageFeedback(message_id=answer.id, rating="down", correction_masked=f"{name} fix"))
                session.add(FlywheelItem(source="thumbs_down", message_id=answer.id,
                                         question_masked=f"{name} question", correction_masked=f"{name} fix"))
                ids[name] = answer.id
            session.add(FlywheelItem(source="reviewer_flag", question_masked="reviewer-written question"))
            await session.commit()

            result = await erase_subject_data(session, admin=admin, subject_id=andi.id)
            assert result["flywheel_items_deleted"] == 1

            left = (await session.scalars(select(FlywheelItem.question_masked))).all()
            assert sorted(left) == ["budi question", "reviewer-written question"]
            assert not any("andi" in (t or "") for t in left)

            entry = await session.scalar(select(AuditEntry).where(AuditEntry.action == "dsr.erase")
                                         .order_by(AuditEntry.seq.desc()).limit(1))
            assert entry.details.get("flywheel_items_deleted") == 1

            await session.execute(delete(FlywheelItem))
            await session.commit()

    _migrate()
    asyncio.run(run())
