from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import back_to_menu_kb
from bot.models import Giveaway, GiveawayStatus, GiveawayType, ParticipationStatus
from bot.services.giveaways import count_participants, get_participation, list_giveaway_participants
from bot.utils.helpers import GIVEAWAY_TYPE_LABELS, format_user
from bot.utils.pagination import paginate


def giveaway_card_text(gw: Giveaway, participants: int = 0) -> str:
    type_label = GIVEAWAY_TYPE_LABELS.get(gw.giveaway_type.value, gw.giveaway_type.value)
    deadline = f"\n⏰ Дедлайн: {gw.deadline.strftime('%d.%m.%Y %H:%M')}" if gw.deadline else ""
    return (
        f"🎁 <b>{gw.title or 'Без названия'}</b>\n"
        f"Тип: {type_label}\n"
        f"{gw.description[:200]}{'...' if len(gw.description) > 200 else ''}\n"
        f"👥 Участников: {participants}{deadline}"
    )


def giveaway_detail_kb(
    gw: Giveaway,
    participation_status: ParticipationStatus | None,
    participation: "Participation | None" = None,
) -> InlineKeyboardMarkup:
    rows = []
    if gw.status == GiveawayStatus.closed:
        if (
            participation
            and participation.status == ParticipationStatus.approved
            and participation.is_winner is True
        ):
            rows.append([InlineKeyboardButton(text="🏆 Вы выиграли!", callback_data="noop")])
        elif (
            participation
            and participation.status == ParticipationStatus.approved
            and participation.is_winner is False
        ):
            rows.append([InlineKeyboardButton(text="😔 Не повезло", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(text="⏹ Завершено", callback_data="noop")])
    elif participation_status == ParticipationStatus.on_review:
        rows.append([InlineKeyboardButton(text="⏳ На проверке", callback_data="noop")])
    elif participation_status == ParticipationStatus.approved:
        if gw.giveaway_type == GiveawayType.randomizer and (
            participation is None or participation.is_winner is None
        ):
            rows.append([InlineKeyboardButton(text="⏳ Ожидает розыгрыша", callback_data="noop")])
        elif participation and participation.is_winner is True:
            rows.append([InlineKeyboardButton(text="🏆 Вы выиграли!", callback_data="noop")])
        elif participation and participation.is_winner is False:
            rows.append([InlineKeyboardButton(text="😔 Не повезло", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(text="✅ Выполнено", callback_data="noop")])
    elif participation_status == ParticipationStatus.in_progress:
        rows.append([InlineKeyboardButton(text="📤 Отправить ответ", callback_data=f"gw:answer:{gw.id}")])
    else:
        rows.append([InlineKeyboardButton(text="✅ Участвовать", callback_data=f"gw:join:{gw.id}")])
    rows.append([InlineKeyboardButton(text="⏰ Напомнить позже", callback_data=f"gw:snooze:{gw.id}")])
    rows.append([InlineKeyboardButton(text="🔙 К списку", callback_data="menu:giveaways")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_giveaway_detail(message: Message, gw: Giveaway, user_db_id: int, session: AsyncSession) -> None:
    part = await get_participation(session, user_db_id, gw.id)
    status = part.status if part else None
    text = giveaway_card_text(gw, await count_participants(session, gw.id))
    if gw.giveaway_type == GiveawayType.randomizer:
        text += "\n🎲 Победитель определяется случайно среди одобренных участников."
        participants = await list_giveaway_participants(
            session, gw.id, approved_only=True
        )
        if participants:
            visible = participants[:20]
            text += "\n\n👥 <b>Участники бинго:</b>\n"
            text += "\n".join(
                f"{index}. {format_user(user)}"
                for index, (_, user) in enumerate(visible, start=1)
            )
            if len(participants) > len(visible):
                text += f"\n…и ещё {len(participants) - len(visible)}"
        else:
            text += "\n\n👥 Участников бинго пока нет."
    kb = giveaway_detail_kb(gw, status, part)
    if gw.media and gw.media.get("type") == "photo":
        await message.answer_photo(gw.media["file_id"], caption=text, reply_markup=kb, parse_mode="HTML")
    elif gw.media and gw.media.get("type") == "video":
        await message.answer_video(gw.media["file_id"], caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
