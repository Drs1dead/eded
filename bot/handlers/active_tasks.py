from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import async_session
from bot.handlers.giveaways_helpers import giveaway_card_text
from bot.keyboards.inline import back_to_menu_kb
from bot.models import GiveawayType, Participation, ParticipationStatus
from bot.services.giveaways import get_giveaway
from bot.services.users import get_user_by_telegram_id
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = Router()


@router.callback_query(F.data == "menu:active_tasks")
async def active_tasks(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            return
        result = await session.execute(
            select(Participation)
            .where(Participation.user_id == user.id)
            .order_by(Participation.created_at.desc())
        )
        parts = list(result.scalars().all())
        active = []
        for p in parts:
            if p.status in (ParticipationStatus.in_progress, ParticipationStatus.on_review):
                active.append(p)
                continue
            if p.status == ParticipationStatus.approved:
                gw = await get_giveaway(session, p.giveaway_id)
                if gw and gw.giveaway_type == GiveawayType.randomizer and p.is_winner is None:
                    active.append(p)

        status_labels = {
            "in_progress": "в процессе",
            "on_review": "на проверке",
        }

        if not active:
            await callback.message.edit_text("📭 Нет активных заданий.", reply_markup=back_to_menu_kb())
            await callback.answer()
            return

        rows = []
        text = "📋 <b>Мои активные задания</b>\n\n"
        for p in active:
            gw = await get_giveaway(session, p.giveaway_id)
            if gw:
                if p.status == ParticipationStatus.approved and p.is_winner is None:
                    status = "ожидает розыгрыша"
                else:
                    status = status_labels.get(p.status.value, p.status.value)
                text += f"• {gw.title} — {status}\n"
                rows.append([
                    InlineKeyboardButton(
                        text=f"▶️ {gw.title[:30]}",
                        callback_data=f"gw:view:{gw.id}",
                    )
                ])
        rows.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:main")])
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    await callback.answer()
