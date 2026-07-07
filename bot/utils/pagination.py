from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def paginate(
    items: list,
    page: int,
    per_page: int,
    prefix: str,
    render_btn,
    back_cb: str = "menu:main",
) -> tuple[list, InlineKeyboardMarkup | None]:
    total = len(items)
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]
    rows = [[render_btn(item)] for item in page_items]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"{prefix}:page:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{prefix}:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_cb)])
    return page_items, InlineKeyboardMarkup(inline_keyboard=rows)


def cb(*parts: str) -> str:
    return ":".join(parts)
