import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_settings (
                chat_id INTEGER PRIMARY KEY,
                anti_spam INTEGER DEFAULT 1,
                anti_flood INTEGER DEFAULT 1,
                max_message_length INTEGER DEFAULT 0,
                flood_limit INTEGER DEFAULT 5,
                flood_window INTEGER DEFAULT 10,
                warn_limit INTEGER DEFAULT 3,
                delete_links INTEGER DEFAULT 0,
                anti_forward INTEGER DEFAULT 0,
                welcome_message TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS free_users (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS staff_roles (
                chat_id  INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                role     TEXT NOT NULL DEFAULT 'mod',
                username TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        # Migrations for existing databases
        for migration in [
            "ALTER TABLE group_settings ADD COLUMN welcome_message TEXT DEFAULT NULL",
            "ALTER TABLE group_settings ADD COLUMN log_channel INTEGER DEFAULT NULL",
        ]:
            try:
                await db.execute(migration)
            except Exception:
                pass  # Column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                user_name     TEXT,
                note_text     TEXT NOT NULL,
                added_by      INTEGER,
                added_by_name TEXT,
                added_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id  INTEGER NOT NULL,
                word     TEXT    NOT NULL,
                action   TEXT    DEFAULT 'warn',
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, word)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id          INTEGER NOT NULL,
                reporter_id      INTEGER NOT NULL,
                reporter_name    TEXT,
                reported_user_id INTEGER,
                reported_name    TEXT,
                message_text     TEXT,
                reason           TEXT,
                reported_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                user_name TEXT,
                messages  INTEGER DEFAULT 0,
                spam      INTEGER DEFAULT 0,
                floods    INTEGER DEFAULT 0,
                mutes     INTEGER DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS personal_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, command_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
                warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def get_settings(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM group_settings WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            await db.execute(
                "INSERT INTO group_settings (chat_id) VALUES (?)", (chat_id,)
            )
            await db.commit()
            return {
                "chat_id": chat_id,
                "anti_spam": 1,
                "anti_flood": 1,
                "max_message_length": 0,
                "flood_limit": 5,
                "flood_window": 10,
                "warn_limit": 3,
                "delete_links": 0,
                "anti_forward": 0,
                "welcome_message": None,
                "log_channel": None,
            }


async def update_setting(chat_id: int, key: str, value) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,)
        )
        await db.execute(
            f"UPDATE group_settings SET {key} = ? WHERE chat_id = ?", (value, chat_id)
        )
        await db.commit()


async def add_warning(chat_id: int, user_id: int, reason: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
            (chat_id, user_id, reason),
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_warnings(chat_id: int, user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY warned_at DESC",
            (chat_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def remove_warning(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY warned_at DESC LIMIT 1",
            (chat_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            await db.execute("DELETE FROM warnings WHERE id = ?", (row[0],))
            await db.commit()
            return True


async def set_staff_role(chat_id: int, user_id: int, role: str, username: str = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO staff_roles (chat_id, user_id, role, username) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, role, username),
        )
        await db.commit()


async def remove_staff_role(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM staff_roles WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_staff_role(chat_id: int, user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role FROM staff_roles WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_all_staff(chat_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, role, username FROM staff_roles WHERE chat_id = ? ORDER BY role",
            (chat_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def add_free_user(chat_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO free_users (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id),
        )
        await db.commit()


async def remove_free_user(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM free_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def is_free_user(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM free_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cursor:
            return await cursor.fetchone() is not None


async def clear_warnings(chat_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()


async def get_all_user_ids(chat_id: int) -> list[int]:
    """Returns all user_ids ever seen in a chat (from user_stats)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM user_stats WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
