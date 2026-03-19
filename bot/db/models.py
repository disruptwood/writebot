import os

import aiosqlite

from bot import config


async def _get_columns(db: aiosqlite.Connection, table_name: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _ensure_column(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    definition: str,
):
    columns = await _get_columns(db, table_name)
    if column_name in columns:
        return
    await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


async def init_db():
    db_path = config.DB_PATH
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                added_by INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_posts (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                author_signature TEXT,
                posted_at TIMESTAMP NOT NULL,
                char_count INTEGER DEFAULT 0,
                resolved_via TEXT
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_user_date
                ON channel_posts(user_id, posted_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_participation (
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                post_count INTEGER DEFAULT 1,
                total_chars INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS streaks (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                current_streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                last_post_date TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                joined_date TEXT,
                status TEXT DEFAULT 'active',
                source TEXT,
                is_active INTEGER DEFAULT 1,
                is_channel_admin INTEGER DEFAULT 0,
                promoted_at TIMESTAMP,
                last_status_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_members_active_status
                ON members(is_active, status)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS member_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT,
                details TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_member_events_user_created
                ON member_events(user_id, created_at)
        """)

        await _ensure_column(db, "channel_posts", "last_name", "TEXT")
        await _ensure_column(db, "channel_posts", "resolved_via", "TEXT")
        await _ensure_column(db, "members", "last_name", "TEXT")
        await _ensure_column(db, "members", "joined_date", "TEXT")
        await _ensure_column(db, "members", "status", "TEXT DEFAULT 'active'")
        await _ensure_column(db, "members", "source", "TEXT")
        await _ensure_column(db, "members", "is_channel_admin", "INTEGER DEFAULT 0")
        await _ensure_column(db, "members", "promoted_at", "TIMESTAMP")
        await _ensure_column(
            db,
            "members",
            "last_status_changed_at",
            "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        )

        await db.execute("""
            UPDATE members
            SET joined_date = COALESCE(joined_date, substr(joined_at, 1, 10))
            WHERE joined_date IS NULL OR joined_date = ''
        """)
        await db.execute("""
            UPDATE members
            SET status = COALESCE(status, 'active')
            WHERE status IS NULL OR status = ''
        """)
        await db.commit()
