"""Создание пользователя и БД clubbot в PostgreSQL."""
import asyncio
import sys

ADMIN_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
TARGET_USER = "clubbot"
TARGET_PASSWORD = "clubbot"
TARGET_DB = "clubbot"


async def main() -> int:
    try:
        import asyncpg
    except ImportError:
        print("Установите asyncpg: pip install asyncpg")
        return 1

    # Пробуем несколько типичных паролей суперпользователя postgres
    admin_urls = [
        "postgresql://postgres:postgres@localhost:5432/postgres",
        "postgresql://postgres:@localhost:5432/postgres",
        "postgresql://postgres:admin@localhost:5432/postgres",
        "postgresql://postgres:123456@localhost:5432/postgres",
    ]

    conn = None
    for url in admin_urls:
        try:
            conn = await asyncpg.connect(url)
            print(f"Подключено: {url.split('@')[0]}@...")
            break
        except Exception:
            continue

    if conn is None:
        print(
            "PostgreSQL недоступен или неверный пароль postgres.\n"
            "Установите PostgreSQL: https://www.postgresql.org/download/windows/\n"
            "Затем выполните в psql от имени postgres:\n"
            f"  CREATE USER {TARGET_USER} WITH PASSWORD '{TARGET_PASSWORD}';\n"
            f"  CREATE DATABASE {TARGET_DB} OWNER {TARGET_USER};"
        )
        return 1

    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", TARGET_USER
        )
        if not exists:
            await conn.execute(
                f"CREATE USER {TARGET_USER} WITH PASSWORD '{TARGET_PASSWORD}'"
            )
            print(f"Пользователь {TARGET_USER} создан.")
        else:
            print(f"Пользователь {TARGET_USER} уже существует.")

        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TARGET_DB
        )
        if not db_exists:
            await conn.execute(f'CREATE DATABASE {TARGET_DB} OWNER "{TARGET_USER}"')
            print(f"База {TARGET_DB} создана.")
        else:
            print(f"База {TARGET_DB} уже существует.")

        print("Готово.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
