import hashlib
from datetime import datetime, timezone


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_username(text: str) -> str:
    return text.strip().lstrip("@").lower()


def format_user(user) -> str:
    if not user:
        return "—"
    if getattr(user, "username", None):
        return f"@{user.username}"
    if getattr(user, "first_name", None):
        return user.first_name
    if getattr(user, "telegram_id", None):
        return f"ID {user.telegram_id}"
    return "—"


def level_from_tasks(count: int) -> int:
    if count >= 50:
        return 5
    if count >= 30:
        return 4
    if count >= 15:
        return 3
    if count >= 5:
        return 2
    return 1


LEVEL_NAMES = {
    1: "Новичок",
    2: "Активный",
    3: "Эксперт",
    4: "Мастер",
    5: "Легенда",
}

GIVEAWAY_TYPE_LABELS = {
    "photo": "С фото",
    "text": "Текстовое",
    "complex": "Сложный",
    "manager": "С обращением к менеджеру",
    "reward": "Задание с наградой",
    "randomizer": "Рандомайзер",
}


def gives_instant_reward(giveaway_type) -> bool:
    value = giveaway_type.value if hasattr(giveaway_type, "value") else str(giveaway_type)
    return value != "randomizer"
