from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import async_session
from bot.models import Gift, GiftDesign, GiftType
from bot.services.users import is_staff
from bot.states.forms import AdminAddGiftStates
from sqlalchemy import select

router = Router()


@router.callback_query(F.data == "admin:gifts")
async def gifts_list(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        gifts = list((await session.execute(select(Gift).where(Gift.is_active.is_(True)))).scalars().all())
        designs = list((await session.execute(select(GiftDesign).where(GiftDesign.is_active.is_(True)))).scalars().all())
        text = "🎁 Подарки:\n"
        for g in gifts:
            text += f"• {g.name} — {g.star_cost} ⭐ ({g.gift_type.value})\n"
        text += f"\n🎨 Оформлений: {len(designs)}"
        rows = [
            [InlineKeyboardButton(text="➕ Добавить подарок", callback_data="admin:gift_add")],
            [InlineKeyboardButton(text="➕ Добавить оформление", callback_data="admin:design_add")],
            [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin:panel")],
        ]
        for g in gifts:
            rows.insert(-1, [
                InlineKeyboardButton(text=f"✏️ {g.name}", callback_data=f"admin:gift_edit:{g.id}"),
                InlineKeyboardButton(text="🗑️", callback_data=f"admin:gift_del:{g.id}"),
            ])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:gift_edit:"))
async def gift_edit(callback: CallbackQuery) -> None:
    await callback.answer(
        "Чтобы изменить подарок: удалите его и создайте заново с нужной стоимостью.",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:gift_add")
async def gift_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(AdminAddGiftStates.enter_name)
    await callback.message.edit_text("Введите название подарка:")
    await callback.answer()


@router.message(AdminAddGiftStates.enter_name)
async def gift_add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await state.set_state(AdminAddGiftStates.enter_cost)
    await message.answer("Введите стоимость в звёздах (число):")


@router.message(AdminAddGiftStates.enter_cost)
async def gift_add_cost(message: Message, state: FSMContext) -> None:
    try:
        cost = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    await state.update_data(star_cost=cost)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Анонимный подарок", callback_data="admin:gift_type:gift")],
            [InlineKeyboardButton(text="💳 На аккаунт", callback_data="admin:gift_type:account")],
        ]
    )
    await state.set_state(AdminAddGiftStates.choose_type)
    await message.answer("Выберите тип:", reply_markup=kb)


@router.callback_query(AdminAddGiftStates.choose_type, F.data.startswith("admin:gift_type:"))
async def gift_add_type(callback: CallbackQuery, state: FSMContext) -> None:
    gift_type = GiftType(callback.data.split(":")[-1])
    data = await state.get_data()
    async with async_session() as session:
        session.add(Gift(name=data["name"], star_cost=data["star_cost"], gift_type=gift_type))
        await session.commit()
    await state.clear()
    await callback.message.edit_text("✅ Подарок добавлен.")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:gift_del:"))
async def gift_delete(callback: CallbackQuery) -> None:
    gid = int(callback.data.split(":")[-1])
    async with async_session() as session:
        g = await session.get(Gift, gid)
        if g:
            g.is_active = False
            await session.commit()
    await callback.answer("Удалено")
    await gifts_list(callback)


@router.callback_query(F.data == "admin:design_add")
async def design_add(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Отправьте название и фото оформления (подпись = название):")
    await callback.answer()


@router.message(F.photo, F.caption)
async def design_add_photo(message: Message) -> None:
    async with async_session() as session:
        if not await is_staff(session, message.from_user.id):
            return
        session.add(GiftDesign(name=message.caption, preview_file_id=message.photo[-1].file_id))
        await session.commit()
    await message.answer("✅ Оформление добавлено.")
