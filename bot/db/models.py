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


async def _table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def _migrate_to_multi_channel(db: aiosqlite.Connection):
    """Migrate single-channel schema to multi-channel by adding channel_id columns."""
    # Check if migration is needed (members table already has channel_id in PK)
    columns = await _get_columns(db, "members")
    if "channel_id" not in columns:
        await _do_multi_channel_migration(db)
        return

    # Check if it's the old schema (channel_id exists but PK is still user_id only)
    async with db.execute("PRAGMA table_info(members)") as cursor:
        rows = await cursor.fetchall()
    pk_cols = [row[1] for row in rows if row[5] > 0]  # col[5] is pk index
    if "channel_id" not in pk_cols:
        await _do_multi_channel_migration(db)


async def _do_multi_channel_migration(db: aiosqlite.Connection):
    """Perform the actual multi-channel migration."""
    default_channel_id = config.CHANNELS[0].channel_id if config.CHANNELS else 0
    default_slug = config.CHANNELS[0].slug if config.CHANNELS else "default"

    # --- channel_posts ---
    await _ensure_column(db, "channel_posts", "channel_id", "INTEGER")
    await db.execute(
        "UPDATE channel_posts SET channel_id = ? WHERE channel_id IS NULL",
        (default_channel_id,),
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS channel_posts_new (
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            author_signature TEXT,
            posted_at TIMESTAMP NOT NULL,
            char_count INTEGER DEFAULT 0,
            resolved_via TEXT,
            PRIMARY KEY (channel_id, message_id)
        )
    """)
    await db.execute("""
        INSERT OR IGNORE INTO channel_posts_new
        SELECT channel_id, message_id, user_id, username, first_name, last_name,
               author_signature, posted_at, char_count, resolved_via
        FROM channel_posts
    """)
    await db.execute("DROP TABLE channel_posts")
    await db.execute("ALTER TABLE channel_posts_new RENAME TO channel_posts")

    # --- daily_participation ---
    await _ensure_column(db, "daily_participation", "channel_id", "INTEGER")
    await db.execute(
        "UPDATE daily_participation SET channel_id = ? WHERE channel_id IS NULL",
        (default_channel_id,),
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_participation_new (
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            post_count INTEGER DEFAULT 1,
            total_chars INTEGER DEFAULT 0,
            PRIMARY KEY (channel_id, user_id, date)
        )
    """)
    await db.execute("""
        INSERT OR IGNORE INTO daily_participation_new
        SELECT channel_id, user_id, date, post_count, total_chars
        FROM daily_participation
    """)
    await db.execute("DROP TABLE daily_participation")
    await db.execute("ALTER TABLE daily_participation_new RENAME TO daily_participation")

    # --- streaks ---
    await _ensure_column(db, "streaks", "channel_id", "INTEGER")
    await db.execute(
        "UPDATE streaks SET channel_id = ? WHERE channel_id IS NULL",
        (default_channel_id,),
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS streaks_new (
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0,
            last_post_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (channel_id, user_id)
        )
    """)
    await db.execute("""
        INSERT OR IGNORE INTO streaks_new
        SELECT channel_id, user_id, username, first_name, current_streak,
               longest_streak, last_post_date, updated_at
        FROM streaks
    """)
    await db.execute("DROP TABLE streaks")
    await db.execute("ALTER TABLE streaks_new RENAME TO streaks")

    # --- members ---
    await _ensure_column(db, "members", "channel_id", "INTEGER")
    await db.execute(
        "UPDATE members SET channel_id = ? WHERE channel_id IS NULL",
        (default_channel_id,),
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS members_new (
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
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
            last_status_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (channel_id, user_id)
        )
    """)
    await db.execute("""
        INSERT OR IGNORE INTO members_new
        SELECT channel_id, user_id, username, first_name, last_name, joined_at,
               joined_date, status, source, is_active, is_channel_admin, promoted_at,
               last_status_changed_at
        FROM members
    """)
    await db.execute("DROP TABLE members")
    await db.execute("ALTER TABLE members_new RENAME TO members")

    # --- member_events ---
    await _ensure_column(db, "member_events", "channel_id", "INTEGER")
    await db.execute(
        "UPDATE member_events SET channel_id = ? WHERE channel_id IS NULL",
        (default_channel_id,),
    )

    # --- bot_state: prefix existing keys with channel slug ---
    async with db.execute("SELECT key, value FROM bot_state") as cursor:
        rows = await cursor.fetchall()
    for key, value in rows:
        if ":" not in key:  # not already prefixed
            new_key = f"{default_slug}:{key}"
            await db.execute(
                "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
                (new_key, value),
            )
            await db.execute("DELETE FROM bot_state WHERE key = ?", (key,))

    # --- Recreate indexes ---
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_posts_channel_user_date
            ON channel_posts(channel_id, user_id, posted_at)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_members_channel_active_status
            ON members(channel_id, is_active, status)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_member_events_channel_user
            ON member_events(channel_id, user_id, created_at)
    """)

    await db.commit()


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
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                author_signature TEXT,
                posted_at TIMESTAMP NOT NULL,
                char_count INTEGER DEFAULT 0,
                resolved_via TEXT,
                PRIMARY KEY (channel_id, message_id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_channel_user_date
                ON channel_posts(channel_id, user_id, posted_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_participation (
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                post_count INTEGER DEFAULT 1,
                total_chars INTEGER DEFAULT 0,
                PRIMARY KEY (channel_id, user_id, date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS streaks (
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                current_streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                last_post_date TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
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
                last_status_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_members_channel_active_status
                ON members(channel_id, is_active, status)
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
                channel_id INTEGER,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT,
                details TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_member_events_channel_user
                ON member_events(channel_id, user_id, created_at)
        """)

        # Run multi-channel migration if needed (for existing DBs)
        await _migrate_to_multi_channel(db)

        await db.commit()
