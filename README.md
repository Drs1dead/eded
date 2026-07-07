# Telegram Club Bot

Закрытый клуб-бот на aiogram 3 + PostgreSQL + Redis.

## Возможности

- Whitelist-доступ и реферальная программа (1 друг, +5 звёзд)
- Розыгрыши с заданиями (фото, текст, сложный, менеджер)
- Публикация в Telegram-каналы
- Модерация розыгрышей и идей
- Профиль, вывод подарков, транзакции звёзд
- Админ-панель со статистикой и досье
- Ежедневный сундук, стрики, уровни, лидерборд
- Планировщик: дедлайны, напоминания, SLA выводов

## Быстрый старт (без Docker)

### 1. PostgreSQL

Установите PostgreSQL и создайте БД:

```sql
CREATE USER clubbot WITH PASSWORD 'clubbot';
CREATE DATABASE clubbot OWNER clubbot;
```

### 2. Redis (опционально)

Для FSM-состояний нужен Redis. Если Redis не запущен, бот автоматически использует память (MemoryStorage) — подходит для локальной разработки.

Windows: скачайте Redis или используйте WSL.

### 3. Настройка

Скопируйте `.env.example` в `.env` и заполните:

```
BOT_TOKEN=...          # токен от @BotFather
ADMIN_IDS=123456789    # ваш Telegram ID
BOT_USERNAME=MyBot     # username бота без @
DATABASE_URL=postgresql+asyncpg://clubbot:clubbot@localhost:5432/clubbot
REDIS_URL=redis://localhost:6379/0
```

### 4. Установка и запуск

```bash
pip install -r requirements.txt
python -m bot
```

При первом запуске таблицы создаются автоматически. ID из `ADMIN_IDS` получают роль admin и доступ в whitelist.

## Структура

- `bot/handlers/` — обработчики пользователя и админа
- `bot/services/` — бизнес-логика
- `bot/models/` — SQLAlchemy ORM
- `bot/schedulers/` — фоновые задачи APScheduler

## Роли

- **Admin** — задаётся через `ADMIN_IDS` в `.env`
- **Manager** — выводы 50+ и задания типа «менеджер»
- **Moderator** — модерация (через таблицу `staff_roles`)

## Рефералка

Ссылка: `https://t.me/BotUsername?start=ref_TELEGRAM_ID`

- Максимум 1 друг на аккаунт
- Друг получает доступ без ручного whitelist
- Пригласивший получает 5 звёзд
