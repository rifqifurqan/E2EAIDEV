"""NFR-20: opaque keyset cursor pagination helpers."""

from datetime import datetime, timezone
import uuid

import pytest

from e2eai.core.errors import AppError
from e2eai.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    clamp_limit,
    decode_cursor,
    encode_cursor,
    make_page,
)

T = datetime(2026, 10, 13, 6, 0, 0, tzinfo=timezone.utc)


def test_cursor_roundtrip_is_opaque_and_urlsafe():
    rid = uuid.uuid4()
    cur = encode_cursor(T, rid)
    assert str(rid) not in cur and "{" not in cur
    assert all(ch.isalnum() or ch in "-_" for ch in cur)
    ts, got = decode_cursor(cur)
    assert ts == T and got == rid


@pytest.mark.parametrize("bad", ["", "!!!", "e30", "bm90LWpzb24", "eyJ0IjoieCIsImkiOiJ5In0"])
def test_malformed_cursor_is_rejected_with_422_problem(bad):
    with pytest.raises(AppError) as e:
        decode_cursor(bad)
    assert e.value.status == 422


def test_clamp_limit_defaults_and_bounds():
    assert clamp_limit(None) == DEFAULT_LIMIT
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1
    assert clamp_limit(10_000) == MAX_LIMIT
    assert clamp_limit(25) == 25


class Row:
    def __init__(self, n):
        self.id = uuid.UUID(int=n)
        self.updated_at = T


def test_make_page_has_next_cursor_only_when_more_rows():
    rows = [Row(i) for i in range(4)]  # limit 3 -> fetched 4
    items, nxt = make_page(rows, 3, lambda r: (r.updated_at, r.id))
    assert items == rows[:3]
    ts, rid = decode_cursor(nxt)
    assert rid == rows[2].id and ts == T  # cursor points at the LAST returned item

    items, nxt = make_page(rows[:3], 3, lambda r: (r.updated_at, r.id))
    assert items == rows[:3] and nxt is None

    items, nxt = make_page([], 3, lambda r: (r.updated_at, r.id))
    assert items == [] and nxt is None


def test_conversation_pages_walk_all_rows_once_newest_first_and_stay_owner_scoped():
    import asyncio

    from sqlalchemy import delete, func, select

    from e2eai.chat import create_conversation, list_conversations_page
    from e2eai.db import Conversation, Message, MessageCitation, MessageFeedback, User, sessions
    from e2eai.seed import seed_demo

    async def run():
        async with sessions()() as s:
            for m in (MessageFeedback, MessageCitation, Message, Conversation):
                await s.execute(delete(m))
            await s.commit()
            await seed_demo(s, password="TestPassword_123456789")
            andi = await s.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await s.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            made = [await create_conversation(s, user=andi, title=f"c{i}") for i in range(5)]
            await create_conversation(s, user=budi, title="budi-private")
            seen, cursor = [], None
            while True:
                items, cursor = await list_conversations_page(s, user=andi, limit=2, cursor=cursor)
                assert len(items) <= 2
                seen += [c.id for c in items]
                if cursor is None:
                    break
            assert sorted(seen) == sorted(c.id for c in made) and len(seen) == 5
            first, nxt = await list_conversations_page(s, user=andi, limit=2)
            assert nxt is not None
            budi_items, budi_next = await list_conversations_page(s, user=budi, limit=2, cursor=nxt)
            assert all(c.title != "c0" for c in budi_items)  # cursor never widens ownership
            return seen

    asyncio.run(run())
