import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import UserDraft


async def save_draft(session: AsyncSession, user_id: int, draft_type: str, data: dict) -> None:
    result = await session.execute(
        select(UserDraft).where(UserDraft.user_id == user_id, UserDraft.draft_type == draft_type)
    )
    draft = result.scalar_one_or_none()
    if draft:
        draft.data = data
    else:
        session.add(UserDraft(user_id=user_id, draft_type=draft_type, data=data))
    await session.flush()


async def load_draft(session: AsyncSession, user_id: int, draft_type: str) -> dict | None:
    result = await session.execute(
        select(UserDraft).where(UserDraft.user_id == user_id, UserDraft.draft_type == draft_type)
    )
    draft = result.scalar_one_or_none()
    return draft.data if draft else None


async def clear_draft(session: AsyncSession, user_id: int, draft_type: str) -> None:
    result = await session.execute(
        select(UserDraft).where(UserDraft.user_id == user_id, UserDraft.draft_type == draft_type)
    )
    draft = result.scalar_one_or_none()
    if draft:
        await session.delete(draft)
