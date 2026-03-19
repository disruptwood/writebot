import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import aiosqlite

from bot import config


def _local_date(dt: datetime | None = None) -> str:
    current = dt or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(ZoneInfo(config.TIMEZONE)).date().isoformat()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _utc_iso(dt: datetime | None = None) -> str:
    current = dt or _utcnow()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).isoformat()


def _row_to_dict(row: aiosqlite.Row | None) -> dict | None:
    return dict(row) if row else None


def _signature_candidates(member: dict) -> set[str]:
    candidates: set[str] = set()

    username = member.get("username")
    first_name = (member.get("first_name") or "").strip()
    last_name = (member.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()

    if username:
        candidates.add(username.strip().lower())
        candidates.add(f"@{username.strip().lower()}")
    if first_name:
        candidates.add(first_name.lower())
    if full_name:
        candidates.add(full_name.lower())

    return {candidate for candidate in candidates if candidate}


async def _log_member_event(
    db: aiosqlite.Connection,
    user_id: int,
    event_type: str,
    source: str | None = None,
    details: dict | None = None,
):
    await db.execute(
        """INSERT INTO member_events (user_id, event_type, source, details, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            user_id,
            event_type,
            source,
            json.dumps(details, ensure_ascii=False, sort_keys=True) if details else None,
            _utc_iso(),
        ),
    )


async def _fetch_member_row(db: aiosqlite.Connection, user_id: int) -> aiosqlite.Row | None:
    async with db.execute(
        "SELECT * FROM members WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        return await cursor.fetchone()


async def _reset_member_progress(db: aiosqlite.Connection, user_id: int):
    await db.execute("DELETE FROM daily_participation WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM streaks WHERE user_id = ?", (user_id,))


# ── Admins ──


async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM admins WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            return await cursor.fetchone() is not None


async def add_admin(
    user_id: int,
    username: str | None,
    first_name: str | None,
    added_by: int,
):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO admins (user_id, username, first_name, added_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name,
                 added_by = excluded.added_by""",
            (user_id, username, first_name, added_by),
        )
        await db.commit()


async def remove_admin(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0


# ── Channel posts ──


async def record_post(
    message_id: int,
    user_id: int | None,
    username: str | None,
    first_name: str | None,
    author_signature: str | None,
    posted_at: datetime,
    char_count: int,
    last_name: str | None = None,
    resolved_via: str | None = None,
):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO channel_posts
               (message_id, user_id, username, first_name, last_name, author_signature,
                posted_at, char_count, resolved_via)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message_id,
                user_id,
                username,
                first_name,
                last_name,
                author_signature,
                _utc_iso(posted_at),
                char_count,
                resolved_via,
            ),
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


async def find_members_by_author_signature(author_signature: str) -> list[dict]:
    normalized = author_signature.strip().lower()
    if not normalized:
        return []

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_id, username, first_name, last_name
               FROM members
               WHERE is_active = 1 AND status = 'active'""",
        ) as cursor:
            members = [dict(row) for row in await cursor.fetchall()]

    matches = []
    for member in members:
        if normalized in _signature_candidates(member):
            matches.append(member)
    return matches


# ── Streaks ──


async def get_user_post_dates(user_id: int) -> list[str]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT date FROM daily_participation WHERE user_id = ? ORDER BY date",
            (user_id,),
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def update_streak(
    user_id: int,
    username: str | None,
    first_name: str | None,
    current: int,
    longest: int,
    last_date: str,
):
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
            (user_id, username, first_name, current, longest, last_date, _utc_iso()),
        )
        await db.commit()


async def get_streak(user_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM streaks WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            return _row_to_dict(await cursor.fetchone())


async def get_leaderboard(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM streaks
               WHERE current_streak > 0
               ORDER BY current_streak DESC, longest_streak DESC
               LIMIT ?""",
            (limit,),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


# ── Members ──


async def upsert_member(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None = None,
):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO members (user_id, username, first_name, last_name)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name,
                 last_name = excluded.last_name""",
            (user_id, username, first_name, last_name),
        )
        await db.commit()


async def create_or_update_pending_member(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None = None,
    source: str = "join_request",
):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        existing = await _fetch_member_row(db, user_id)

        if existing and existing["is_active"] == 1 and existing["status"] == "active":
            await db.execute(
                """UPDATE members
                   SET username = ?, first_name = ?, last_name = ?, source = ?
                   WHERE user_id = ?""",
                (username, first_name, last_name, source, user_id),
            )
        else:
            now_iso = _utc_iso()
            await db.execute(
                """INSERT INTO members (
                       user_id, username, first_name, last_name, joined_at, joined_date,
                       status, source, is_active, is_channel_admin, promoted_at,
                       last_status_changed_at
                   )
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 0, 0, NULL, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     username = excluded.username,
                     first_name = excluded.first_name,
                     last_name = excluded.last_name,
                     status = 'pending',
                     source = excluded.source,
                     is_active = 0,
                     is_channel_admin = 0,
                     promoted_at = NULL,
                     last_status_changed_at = excluded.last_status_changed_at""",
                (
                    user_id,
                    username,
                    first_name,
                    last_name,
                    now_iso,
                    _local_date(),
                    source,
                    now_iso,
                ),
            )
            await _log_member_event(
                db,
                user_id,
                "pending_join_request",
                source=source,
            )

        await db.commit()


async def activate_member(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None = None,
    joined_at: datetime | None = None,
    source: str = "chat_member",
    reset_progress: bool = False,
) -> bool:
    joined_at = joined_at or _utcnow()
    joined_iso = _utc_iso(joined_at)
    joined_date = _local_date(joined_at)

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        existing = await _fetch_member_row(db, user_id)

        should_reset = bool(
            reset_progress
            or (
                existing
                and not (existing["is_active"] == 1 and existing["status"] == "active")
            )
        )

        if should_reset:
            await _reset_member_progress(db, user_id)

        if should_reset or not existing:
            await db.execute(
                """INSERT INTO members (
                       user_id, username, first_name, last_name, joined_at, joined_date,
                       status, source, is_active, is_channel_admin, promoted_at,
                       last_status_changed_at
                   )
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 1, 0, NULL, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     username = excluded.username,
                     first_name = excluded.first_name,
                     last_name = excluded.last_name,
                     joined_at = excluded.joined_at,
                     joined_date = excluded.joined_date,
                     status = 'active',
                     source = excluded.source,
                     is_active = 1,
                     is_channel_admin = 0,
                     promoted_at = NULL,
                     last_status_changed_at = excluded.last_status_changed_at""",
                (
                    user_id,
                    username,
                    first_name,
                    last_name,
                    joined_iso,
                    joined_date,
                    source,
                    joined_iso,
                ),
            )
        else:
            await db.execute(
                """UPDATE members
                   SET username = ?, first_name = ?, last_name = ?, source = ?,
                       is_active = 1, status = 'active'
                   WHERE user_id = ?""",
                (username, first_name, last_name, source, user_id),
            )

        await _log_member_event(
            db,
            user_id,
            "activated" if should_reset or not existing else "synced_active",
            source=source,
            details={"progress_reset": should_reset},
        )
        await db.commit()
        return should_reset


async def set_member_channel_admin(
    user_id: int,
    is_channel_admin: bool,
    source: str = "promotion",
):
    promoted_at = _utc_iso() if is_channel_admin else None
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """UPDATE members
               SET is_channel_admin = ?, promoted_at = ?
               WHERE user_id = ?""",
            (1 if is_channel_admin else 0, promoted_at, user_id),
        )
        await _log_member_event(
            db,
            user_id,
            "promotion_succeeded" if is_channel_admin else "demoted",
            source=source,
        )
        await db.commit()


async def mark_member_status(
    user_id: int,
    status: str,
    source: str,
):
    is_active = 1 if status == "active" else 0
    now_iso = _utc_iso()

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """UPDATE members
               SET status = ?, source = ?, is_active = ?, is_channel_admin = 0,
                   promoted_at = NULL, last_status_changed_at = ?
               WHERE user_id = ?""",
            (status, source, is_active, now_iso, user_id),
        )
        await _log_member_event(
            db,
            user_id,
            f"status_{status}",
            source=source,
        )
        await db.commit()


async def reset_member_progress(user_id: int, source: str = "manual_reset"):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _reset_member_progress(db, user_id)
        await _log_member_event(
            db,
            user_id,
            "progress_reset",
            source=source,
        )
        await db.commit()


async def deactivate_member(user_id: int):
    await mark_member_status(user_id, "inactive", source="manual_deactivate")


async def reactivate_member(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        existing = await _fetch_member_row(db, user_id)
        if not existing:
            return
    await activate_member(
        user_id=user_id,
        username=existing["username"],
        first_name=existing["first_name"],
        last_name=existing["last_name"],
        source="manual_reactivate",
        reset_progress=True,
    )


async def get_member(user_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM members WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            return _row_to_dict(await cursor.fetchone())


async def get_active_members() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT *
               FROM members
               WHERE is_active = 1 AND status = 'active'
               ORDER BY first_name, username, user_id""",
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_members_pending_promotion() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT *
               FROM members
               WHERE is_active = 1
                 AND status = 'active'
                 AND is_channel_admin = 0
               ORDER BY joined_at, user_id""",
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_pending_members() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT *
               FROM members
               WHERE is_active = 0
                 AND status = 'pending'
               ORDER BY last_status_changed_at, user_id""",
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_today_writers(today: str) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT dp.user_id, m.username, m.first_name, m.last_name, dp.post_count
               FROM daily_participation dp
               LEFT JOIN members m ON dp.user_id = m.user_id
               WHERE dp.date = ?
               ORDER BY dp.post_count DESC, m.first_name, m.user_id""",
            (today,),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_missing_today(today: str) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.user_id, m.username, m.first_name, m.last_name
               FROM members m
               LEFT JOIN daily_participation dp
                 ON m.user_id = dp.user_id AND dp.date = ?
               WHERE m.is_active = 1
                 AND m.status = 'active'
                 AND dp.user_id IS NULL
               ORDER BY m.first_name, m.username, m.user_id""",
            (today,),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_member_compliance_snapshots() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.user_id, m.username, m.first_name, m.last_name,
                      m.joined_date, m.joined_at, m.is_channel_admin,
                      s.last_post_date
               FROM members m
               LEFT JOIN streaks s ON m.user_id = s.user_id
               WHERE m.is_active = 1 AND m.status = 'active'
               ORDER BY m.joined_at, m.user_id""",
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_inactive_members(days: int) -> list[dict]:
    today = _local_date()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.user_id, m.username, m.first_name, m.last_name,
                      s.last_post_date, s.current_streak
               FROM members m
               LEFT JOIN streaks s ON m.user_id = s.user_id
               WHERE m.is_active = 1
                 AND m.status = 'active'
                 AND (s.last_post_date IS NULL
                      OR julianday(?) - julianday(s.last_post_date) >= ?)""",
            (today, days),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


# ── Bot state ──


async def get_state(key: str) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM bot_state WHERE key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_state(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO bot_state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        await db.commit()
