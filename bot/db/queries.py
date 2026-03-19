from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite

from bot import config


def _today_israel() -> str:
    """Today's date in configured timezone."""
    return datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()


# ── Admins ──

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def add_admin(user_id: int, username: str | None, first_name: str | None, added_by: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO admins (user_id, username, first_name, added_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name""",
            (user_id, username, first_name, added_by),
        )
        await db.commit()


async def remove_admin(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()
        return cur.rowcount > 0


# ── Channel posts ──

async def record_post(message_id: int, user_id: int | None, username: str | None,
                      first_name: str | None, author_signature: str | None,
                      posted_at: datetime, char_count: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO channel_posts
               (message_id, user_id, username, first_name, author_signature, posted_at, char_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (message_id, user_id, username, first_name, author_signature,
             posted_at.isoformat(), char_count),
        )
        await db.commit()


async def upsert_daily_participation(user_id: int, day: str, char_count: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO daily_participation (user_id, date, post_count, total_chars)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, date) DO UPDATE SET
                 post_count = post_count + 1,
                 total_chars = total_chars + excluded.total_chars""",
            (user_id, day, char_count),
        )
        await db.commit()


# ── Streaks ──

async def get_user_post_dates(user_id: int) -> list[str]:
    """Return sorted list of ISO date strings when user posted."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT date FROM daily_participation WHERE user_id = ? ORDER BY date",
            (user_id,),
        ) as cur:
            return [row[0] for row in await cur.fetchall()]


async def update_streak(user_id: int, username: str | None, first_name: str | None,
                        current: int, longest: int, last_date: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO streaks (user_id, username, first_name, current_streak,
                                    longest_streak, last_post_date, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name,
                 current_streak = excluded.current_streak,
                 longest_streak = excluded.longest_streak,
                 last_post_date = excluded.last_post_date,
                 updated_at = excluded.updated_at""",
            (user_id, username, first_name, current, longest, last_date,
             datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_streak(user_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM streaks WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_leaderboard(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM streaks
               WHERE current_streak > 0
               ORDER BY current_streak DESC, longest_streak DESC
               LIMIT ?""",
            (limit,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


# ── Members ──

async def upsert_member(user_id: int, username: str | None, first_name: str | None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO members (user_id, username, first_name)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name""",
            (user_id, username, first_name),
        )
        await db.commit()


async def get_active_members() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM members WHERE is_active = 1"
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_today_writers(today: str) -> list[dict]:
    """Get users who posted today."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT dp.user_id, s.username, s.first_name, dp.post_count
               FROM daily_participation dp
               LEFT JOIN streaks s ON dp.user_id = s.user_id
               WHERE dp.date = ?""",
            (today,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_missing_today(today: str) -> list[dict]:
    """Get active members who haven't posted today."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.user_id, m.username, m.first_name
               FROM members m
               LEFT JOIN daily_participation dp
                 ON m.user_id = dp.user_id AND dp.date = ?
               WHERE m.is_active = 1 AND dp.user_id IS NULL""",
            (today,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def deactivate_member(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE members SET is_active = 0 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def reactivate_member(user_id: int):
    """Re-enable a previously kicked member."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE members SET is_active = 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def get_inactive_members(days: int) -> list[dict]:
    """Members who haven't posted in the last N days (Israel time)."""
    today = _today_israel()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.user_id, m.username, m.first_name,
                      s.last_post_date, s.current_streak
               FROM members m
               LEFT JOIN streaks s ON m.user_id = s.user_id
               WHERE m.is_active = 1
                 AND (s.last_post_date IS NULL
                      OR julianday(?) - julianday(s.last_post_date) >= ?)""",
            (today, days),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_member(user_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM members WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ── Bot state (scheduler persistence) ──

async def get_state(key: str) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_state(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO bot_state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        await db.commit()
