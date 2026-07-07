from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database import async_session
from bot.keyboards.inline import admin_panel_kb, back_to_menu_kb
from bot.models import GiveawayProposal, Idea, ModerationStatus
from bot.services.users import is_staff
from bot.services.withdrawals import count_pending_withdrawals
from sqlalchemy import func, select
from bot.models import Giveaway, GiveawayStatus

router = Router()


async def get_admin_counts(session) -> dict:
    proposals = await session.execute(
        select(func.count()).where(GiveawayProposal.status == ModerationStatus.pending)
    )
    ideas = await session.execute(select(func.count()).where(Idea.status == ModerationStatus.pending))
    withdrawals = await count_pending_withdrawals(session)
    return {
        "proposals": proposals.scalar() or 0,
        "ideas": ideas.scalar() or 0,
        "withdrawals": withdrawals,
    }


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        counts = await get_admin_counts(session)
    await callback.message.edit_text("⚙️ Админ-панель", reply_markup=admin_panel_kb(counts))
    await callback.answer()
