"""Integration tests for DB queries against temp SQLite."""

from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a temp file DB for each test."""
    db_path = str(tmp_path / "test.db")

    from bot import config
    config.DB_PATH = db_path

    from bot.db.models import init_db
    await init_db()
    yield


class TestAdminQueries:
    async def test_add_and_check_admin(self):
        from bot.db.queries import add_admin, is_admin
        assert not await is_admin(123)
        await add_admin(123, "testuser", "Test", 0)
        assert await is_admin(123)

    async def test_remove_admin(self):
        from bot.db.queries import add_admin, remove_admin, is_admin
        await add_admin(123, "testuser", "Test", 0)
        assert await remove_admin(123)
        assert not await is_admin(123)

    async def test_remove_nonexistent(self):
        from bot.db.queries import remove_admin
        assert not await remove_admin(999)


class TestPostQueries:
    async def test_record_post_with_user(self):
        from bot.db.queries import record_post, upsert_daily_participation, get_user_post_dates

        await record_post(1, 100, "alice", "Alice", None, datetime(2024, 1, 15, 10, 0), 42)
        await upsert_daily_participation(100, "2024-01-15", 42)

        dates = await get_user_post_dates(100)
        assert dates == ["2024-01-15"]

    async def test_record_post_without_user(self):
        """Posts without user_id (anonymous channel posts) should be saved."""
        from bot.db.queries import record_post
        # Should not raise
        await record_post(1, None, None, None, "Some Author", datetime(2024, 1, 15, 10, 0), 100)

    async def test_participation_aggregates(self):
        from bot.db.queries import upsert_daily_participation, get_user_post_dates

        await upsert_daily_participation(100, "2024-01-15", 10)
        await upsert_daily_participation(100, "2024-01-15", 20)
        await upsert_daily_participation(100, "2024-01-16", 5)

        dates = await get_user_post_dates(100)
        assert dates == ["2024-01-15", "2024-01-16"]


class TestMemberQueries:
    async def test_upsert_and_list(self):
        from bot.db.queries import upsert_member, get_active_members

        await upsert_member(100, "alice", "Alice")
        await upsert_member(200, "bob", "Bob")

        members = await get_active_members()
        assert len(members) == 2

    async def test_deactivate(self):
        from bot.db.queries import upsert_member, deactivate_member, get_active_members

        await upsert_member(100, "alice", "Alice")
        await deactivate_member(100)

        members = await get_active_members()
        assert len(members) == 0

    async def test_reactivate(self):
        from bot.db.queries import upsert_member, deactivate_member, reactivate_member, get_active_members

        await upsert_member(100, "alice", "Alice")
        await deactivate_member(100)
        assert len(await get_active_members()) == 0

        await reactivate_member(100)
        assert len(await get_active_members()) == 1

    async def test_get_member(self):
        from bot.db.queries import upsert_member, get_member

        await upsert_member(100, "alice", "Alice")
        m = await get_member(100)
        assert m is not None
        assert m["username"] == "alice"

        assert await get_member(999) is None

    async def test_missing_today(self):
        from bot.db.queries import upsert_member, upsert_daily_participation, get_missing_today

        await upsert_member(100, "alice", "Alice")
        await upsert_member(200, "bob", "Bob")
        await upsert_daily_participation(100, "2024-01-15", 10)

        missing = await get_missing_today("2024-01-15")
        assert len(missing) == 1
        assert missing[0]["user_id"] == 200


class TestStreakQueries:
    async def test_update_and_get_streak(self):
        from bot.db.queries import update_streak, get_streak

        await update_streak(100, "alice", "Alice", 5, 10, "2024-01-15")

        streak = await get_streak(100)
        assert streak is not None
        assert streak["current_streak"] == 5
        assert streak["longest_streak"] == 10

    async def test_leaderboard(self):
        from bot.db.queries import update_streak, get_leaderboard

        await update_streak(100, "alice", "Alice", 5, 5, "2024-01-15")
        await update_streak(200, "bob", "Bob", 3, 7, "2024-01-15")
        await update_streak(300, "carol", "Carol", 0, 2, "2024-01-10")

        leaders = await get_leaderboard()
        assert len(leaders) == 2  # carol excluded (current_streak=0)
        assert leaders[0]["user_id"] == 100  # alice first (streak=5)


class TestBotState:
    async def test_get_set_state(self):
        from bot.db.queries import get_state, set_state

        assert await get_state("foo") is None
        await set_state("foo", "bar")
        assert await get_state("foo") == "bar"

    async def test_state_upsert(self):
        from bot.db.queries import get_state, set_state

        await set_state("key", "value1")
        await set_state("key", "value2")
        assert await get_state("key") == "value2"
