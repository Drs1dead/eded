from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database import async_session
from bot.services.users import is_whitelisted


class WhitelistMiddleware(BaseMiddleware):
    ALLOWED = {"/start", "/help"}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            if event.text and any(event.text.startswith(c) for c in self.ALLOWED):
                return await handler(event, data)
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            cb = event.data or ""
            if cb.startswith("task:accept:") or cb.startswith("channel:"):
                return await handler(event, data)
            user_id = event.from_user.id if event.from_user else None

        if user_id is None:
            return await handler(event, data)

        async with async_session() as session:
            if await is_whitelisted(session, user_id):
                data["db_user_whitelisted"] = True
                return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещён", show_alert=True)
            return None
        if isinstance(event, Message):
            await event.answer("⛔ Доступ запрещён. Вы не в whitelist.")
            return None
        return None
