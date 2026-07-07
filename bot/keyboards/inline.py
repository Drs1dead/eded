from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.helpers import LEVEL_NAMES


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎁 Розыгрыши", callback_data="menu:giveaways")],
        [InlineKeyboardButton(text="📋 Мои активные задания", callback_data="menu:active_tasks")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu:profile")],
        [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="menu:referral")],
        [InlineKeyboardButton(text="📝 Предложить розыгрыш", callback_data="menu:propose_giveaway")],
        [InlineKeyboardButton(text="💡 Предложить идею", callback_data="menu:propose_idea")],
        [InlineKeyboardButton(text="🎒 Сундук", callback_data="menu:chest")],
        [InlineKeyboardButton(text="🏆 Лидерборд", callback_data="menu:leaderboard")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu:support")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:main")]]
    )


def giveaway_types_kb(prefix: str = "gw_type") -> InlineKeyboardMarkup:
    types = [
        ("reward", "✅ Задание с наградой"),
        ("randomizer", "🎲 Рандомайзер"),
        ("photo", "📷 С фото"),
        ("text", "📝 Текстовое"),
        ("complex", "🧩 Сложный"),
        ("manager", "👔 С обращением к менеджеру"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"{prefix}:{t}")] for t, label in types]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(yes_cb: str, no_cb: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=yes_cb),
                InlineKeyboardButton(text="❌ Нет", callback_data=no_cb),
            ]
        ]
    )


def admin_panel_kb(counts: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Создать розыгрыш", callback_data="admin:create_gw")],
            [InlineKeyboardButton(text="⏹ Активные розыгрыши", callback_data="admin:active_gw")],
            [InlineKeyboardButton(text=f"📌 Модерация розыгрышей ({counts.get('proposals', 0)})", callback_data="admin:mod_gw")],
            [InlineKeyboardButton(text=f"💡 Модерация идей ({counts.get('ideas', 0)})", callback_data="admin:mod_ideas")],
            [InlineKeyboardButton(text="📣 Управление каналами", callback_data="admin:channels")],
            [InlineKeyboardButton(text="🎁 Управление подарками", callback_data="admin:gifts")],
            [InlineKeyboardButton(text="👥 Whitelist", callback_data="admin:whitelist")],
            [InlineKeyboardButton(text=f"📊 Статистика ({counts.get('withdrawals', 0)} выводов)", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🔧 Health-check каналов", callback_data="admin:health")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:main")],
        ]
    )


def moderation_actions_kb(entity: str, entity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"mod:{entity}:approve:{entity_id}"),
                InlineKeyboardButton(text="✏️ Переработать", callback_data=f"mod:{entity}:rework:{entity_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod:{entity}:reject:{entity_id}"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:panel")],
        ]
    )
