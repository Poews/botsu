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
        # Migrate existing databases that don't have the welcome_message column yet
        try:
            await db.execute("ALTER TABLE group_settings ADD COLUMN welcome_message TEXT DEFAULT NULL")
        except Exception:
            pass  # Column already exists
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


async def clear_warnings(chat_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()
