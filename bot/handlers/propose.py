from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import async_session
from bot.keyboards.inline import back_to_menu_kb, confirm_kb, giveaway_types_kb
from bot.models import GiveawayProposal, GiveawayType, Idea, ModerationStatus
from bot.services.users import get_user_by_telegram_id
from bot.services.withdrawals import is_content_blocked
from bot.states.forms import ProposeGiveawayStates, ProposeIdeaStates
from bot.utils.helpers import content_hash

router = Router()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "menu:propose_giveaway")
async def start_propose_giveaway(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        from bot.services.drafts import load_draft
        from bot.services.users import get_user_by_telegram_id

        user = await get_user_by_telegram_id(session, callback.from_user.id)
        draft = await load_draft(session, user.id, "propose_giveaway") if user else None
        if draft:
            rows = [
                [InlineKeyboardButton(text="📋 Продолжить черновик", callback_data="prop:resume_draft")],
                [InlineKeyboardButton(text="🆕 Новый розыгрыш", callback_data="prop:new")],
            ]
            await callback.message.edit_text(
                "У вас есть черновик. Продолжить?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
            await callback.answer()
            return
    await state.set_state(ProposeGiveawayStates.choose_type)
    await callback.message.edit_text("Выберите тип розыгрыша:", reply_markup=giveaway_types_kb("prop_type"))
    await callback.answer()


@router.callback_query(F.data == "prop:new")
async def propose_new(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(ProposeGiveawayStates.choose_type)
    await callback.message.edit_text("Выберите тип розыгрыша:", reply_markup=giveaway_types_kb("prop_type"))
    await callback.answer()


@router.callback_query(F.data == "prop:resume_draft")
async def propose_resume(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        from bot.services.drafts import load_draft
        from bot.services.users import get_user_by_telegram_id

        user = await get_user_by_telegram_id(session, callback.from_user.id)
        draft = await load_draft(session, user.id, "propose_giveaway")
        if draft:
            await state.update_data(**draft)
            await state.set_state(ProposeGiveawayStates.confirm)
            await callback.message.edit_text(
                f"Черновик:\n<b>{draft.get('title', '')}</b>",
                reply_markup=confirm_kb("prop:confirm", "menu:main"),
                parse_mode="HTML",
            )
    await callback.answer()


@router.callback_query(ProposeGiveawayStates.choose_type, F.data.startswith("prop_type:"))
async def propose_choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    gw_type = callback.data.split(":")[-1]
    await state.update_data(giveaway_type=gw_type)
    await state.set_state(ProposeGiveawayStates.enter_title)
    await callback.message.edit_text("Введите название розыгрыша:")
    await callback.answer()


@router.message(ProposeGiveawayStates.enter_title)
async def propose_enter_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    data = await state.get_data()
    async with async_session() as session:
        from bot.services.drafts import save_draft
        from bot.services.users import get_user_by_telegram_id

        user = await get_user_by_telegram_id(session, message.from_user.id)
        if user:
            await save_draft(session, user.id, "propose_giveaway", data)
            await session.commit()
    await state.set_state(ProposeGiveawayStates.enter_content)
    await message.answer("Введите описание (текст задания):")


@router.message(ProposeGiveawayStates.enter_content)
async def propose_enter_content(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text)
    data = await state.get_data()
    if data.get("giveaway_type") in ("photo", "complex"):
        await state.set_state(ProposeGiveawayStates.enter_media)
        await message.answer("Отправьте фото или видео:")
        return
    await state.set_state(ProposeGiveawayStates.confirm)
    await message.answer(
        f"Подтвердите отправку:\n\n<b>{data.get('title')}</b>\n{message.text}",
        reply_markup=confirm_kb("prop:confirm", "menu:main"),
        parse_mode="HTML",
    )


@router.message(ProposeGiveawayStates.enter_media)
async def propose_enter_media(message: Message, state: FSMContext) -> None:
    media = None
    if message.photo:
        media = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        media = {"type": "video", "file_id": message.video.file_id}
    await state.update_data(media=media)
    data = await state.get_data()
    await state.set_state(ProposeGiveawayStates.confirm)
    await message.answer(
        f"Подтвердите отправку:\n\n<b>{data.get('title')}</b>",
        reply_markup=confirm_kb("prop:confirm", "menu:main"),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "prop:confirm")
async def propose_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    data = await state.get_data()
    text_for_hash = f"{data.get('title')}{data.get('description')}{data.get('giveaway_type')}"
    h = content_hash(text_for_hash)

    async with async_session() as session:
        if await is_content_blocked(session, h):
            await callback.message.edit_text(
                "⛔ Этот контент был ранее отклонён и не может быть отправлен повторно.",
                reply_markup=back_to_menu_kb(),
            )
            await state.clear()
            await callback.answer()
            return

        user = await get_user_by_telegram_id(session, callback.from_user.id)
        proposal = GiveawayProposal(
            author_id=user.id,
            giveaway_type=GiveawayType(data.get("giveaway_type")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            media=data.get("media"),
            content_hash=h,
        )
        session.add(proposal)
        from bot.services.drafts import clear_draft

        await clear_draft(session, user.id, "propose_giveaway")
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        "✅ Ваш розыгрыш отправлен на модерацию.",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:propose_idea")
async def start_propose_idea(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(ProposeIdeaStates.enter_text)
    await callback.message.edit_text("💡 Опишите вашу идею:")
    await callback.answer()


@router.message(ProposeIdeaStates.enter_text)
async def propose_idea_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    h = content_hash(message.text)
    async with async_session() as session:
        if await is_content_blocked(session, h):
            await message.answer("⛔ Эта идея была ранее отклонена.")
            await state.clear()
            return
        user = await get_user_by_telegram_id(session, message.from_user.id)
        session.add(Idea(author_id=user.id, text=message.text, content_hash=h))
        await session.commit()
    await state.clear()
    await message.answer("✅ Ваша идея отправлена.", reply_markup=back_to_menu_kb())
