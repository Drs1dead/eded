from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._last: dict[int, datetime] = defaultdict(lambda: datetime.min)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
        uid = event.from_user.id
        now = datetime.utcnow()
        if now - self._last[uid] < timedelta(seconds=self.rate_limit):
            return None
        self._last[uid] = now
        return await handler(event, data)
