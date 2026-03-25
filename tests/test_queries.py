"""Integration tests for DB queries against temp SQLite."""

from datetime import datetime

import pytest_asyncio

from tests.conftest import TEST_CHANNEL_ID, TEST_CHANNEL_ID_2

CH = TEST_CHANNEL_ID
CH2 = TEST_CHANNEL_ID_2


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a temp file DB for each test."""
    db_path = str(tmp_path / "test.db")

    from bot import config
    from bot.config import ChannelConfig

    config.DB_PATH = db_path
    config.CHANNELS = [
        ChannelConfig(
            slug="test", channel_id=CH, discussion_group_id=-1009876543210,
            reminder_chat_id=-1009876543210, name="Test", invite_link_name="test-main",
            private_commands=True, manual_member_ids=[],
        ),
        ChannelConfig(
            slug="test2", channel_id=CH2, discussion_group_id=-1009876543211,
            reminder_chat_id=-1009876543211, name="Test 2", invite_link_name="test2-main",
            private_commands=False, manual_member_ids=[],
        ),
    ]
    config._CHANNEL_BY_CHANNEL_ID = {ch.channel_id: ch for ch in config.CHANNELS}
    config._CHANNEL_BY_GROUP_ID = {ch.discussion_group_id: ch for ch in config.CHANNELS}
    config.ALL_CHANNEL_IDS = {ch.channel_id for ch in config.CHANNELS}
    config.ALL_GROUP_IDS = {ch.discussion_group_id for ch in config.CHANNELS}

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

        await record_post(CH, 1, 100, "alice", "Alice", None, datetime(2024, 1, 15, 10, 0), 42)
        await upsert_daily_participation(CH, 100, "2024-01-15", 42)

        dates = await get_user_post_dates(CH, 100)
        assert dates == ["2024-01-15"]

    async def test_record_post_without_user(self):
        """Posts without user_id (anonymous channel posts) should be saved."""
        from bot.db.queries import record_post
        await record_post(CH, 1, None, None, None, "Some Author", datetime(2024, 1, 15, 10, 0), 100)

    async def test_participation_aggregates(self):
        from bot.db.queries import upsert_daily_participation, get_user_post_dates

        await upsert_daily_participation(CH, 100, "2024-01-15", 10)
        await upsert_daily_participation(CH, 100, "2024-01-15", 20)
        await upsert_daily_participation(CH, 100, "2024-01-16", 5)

        dates = await get_user_post_dates(CH, 100)
        assert dates == ["2024-01-15", "2024-01-16"]


class TestMemberQueries:
    async def test_upsert_and_list(self):
        from bot.db.queries import upsert_member, get_active_members

        await upsert_member(CH, 100, "alice", "Alice")
        await upsert_member(CH, 200, "bob", "Bob")

        members = await get_active_members(CH)
        assert len(members) == 2

    async def test_deactivate(self):
        from bot.db.queries import upsert_member, deactivate_member, get_active_members

        await upsert_member(CH, 100, "alice", "Alice")
        await deactivate_member(CH, 100)

        members = await get_active_members(CH)
        assert len(members) == 0

    async def test_reactivate(self):
        from bot.db.queries import upsert_member, deactivate_member, reactivate_member, get_active_members

        await upsert_member(CH, 100, "alice", "Alice")
        await deactivate_member(CH, 100)
        assert len(await get_active_members(CH)) == 0

        await reactivate_member(CH, 100)
        assert len(await get_active_members(CH)) == 1

    async def test_get_member(self):
        from bot.db.queries import upsert_member, get_member

        await upsert_member(CH, 100, "alice", "Alice")
        m = await get_member(CH, 100)
        assert m is not None
        assert m["username"] == "alice"

        assert await get_member(CH, 999) is None

    async def test_missing_today(self):
        from bot.db.queries import upsert_member, upsert_daily_participation, get_missing_today

        await upsert_member(CH, 100, "alice", "Alice")
        await upsert_member(CH, 200, "bob", "Bob")
        await upsert_daily_participation(CH, 100, "2024-01-15", 10)

        missing = await get_missing_today(CH, "2024-01-15")
        assert len(missing) == 1
        assert missing[0]["user_id"] == 200

    async def test_pending_member_and_promotion_queue(self):
        from bot.db.queries import (
            create_or_update_pending_member,
            get_members_pending_promotion,
            get_pending_members,
            set_member_channel_admin,
            activate_member,
        )

        await create_or_update_pending_member(CH, 100, "alice", "Alice", "A")
        pending = await get_pending_members(CH)
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

        await activate_member(CH, 100, "alice", "Alice", "A", source="test_activation")
        queued = await get_members_pending_promotion(CH)
        assert len(queued) == 1
        assert queued[0]["user_id"] == 100

        await set_member_channel_admin(CH, 100, True, source="test_promotion")
        assert await get_members_pending_promotion(CH) == []

    async def test_rejoin_resets_progress(self):
        from bot.db.queries import (
            activate_member,
            get_member,
            get_streak,
            get_user_post_dates,
            mark_member_status,
            update_streak,
            upsert_daily_participation,
        )

        await activate_member(CH, 100, "alice", "Alice", "A", source="initial_join")
        await upsert_daily_participation(CH, 100, "2024-01-15", 10)
        await update_streak(CH, 100, "alice", "Alice", 1, 3, "2024-01-15")

        await mark_member_status(CH, 100, "kicked", source="test_kick")
        await activate_member(CH, 100, "alice", "Alice", "A", source="rejoin")

        member = await get_member(CH, 100)
        assert member is not None
        assert member["status"] == "active"
        assert member["is_active"] == 1
        assert member["is_channel_admin"] == 0
        assert await get_user_post_dates(CH, 100) == []
        assert await get_streak(CH, 100) is None

    async def test_signature_lookup_requires_unique_match(self):
        from bot.db.queries import activate_member, find_members_by_author_signature

        await activate_member(CH, 100, "alice", "Alice", "Smith", source="join")
        await activate_member(CH, 200, "bob", "Bob", "Stone", source="join")

        matches = await find_members_by_author_signature(CH, "Alice Smith")
        assert [member["user_id"] for member in matches] == [100]

        await activate_member(CH, 300, None, "Alice", "Smith", source="join")
        matches = await find_members_by_author_signature(CH, "Alice Smith")
        assert sorted(member["user_id"] for member in matches) == [100, 300]


class TestStreakQueries:
    async def test_update_and_get_streak(self):
        from bot.db.queries import update_streak, get_streak

        await update_streak(CH, 100, "alice", "Alice", 5, 10, "2024-01-15")

        streak = await get_streak(CH, 100)
        assert streak is not None
        assert streak["current_streak"] == 5
        assert streak["longest_streak"] == 10

    async def test_leaderboard(self):
        from bot.db.queries import update_streak, get_leaderboard

        await update_streak(CH, 100, "alice", "Alice", 5, 5, "2024-01-15")
        await update_streak(CH, 200, "bob", "Bob", 3, 7, "2024-01-15")
        await update_streak(CH, 300, "carol", "Carol", 0, 2, "2024-01-10")

        leaders = await get_leaderboard(CH)
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


class TestCrossChannelStreaks:
    """Cross-channel streak sharing: posts in any channel count toward streaks."""

    async def test_post_dates_cross_channel_aggregates_both(self):
        """get_user_post_dates_cross_channel returns dates from all channels."""
        from bot.db.queries import upsert_daily_participation, get_user_post_dates_cross_channel

        await upsert_daily_participation(CH, 100, "2024-01-15", 10)
        await upsert_daily_participation(CH2, 100, "2024-01-16", 20)

        dates = await get_user_post_dates_cross_channel(100)
        assert dates == ["2024-01-15", "2024-01-16"]

    async def test_post_dates_per_channel_stays_filtered(self):
        """get_user_post_dates still returns only the specified channel's dates."""
        from bot.db.queries import upsert_daily_participation, get_user_post_dates

        await upsert_daily_participation(CH, 100, "2024-01-15", 10)
        await upsert_daily_participation(CH2, 100, "2024-01-16", 20)

        assert await get_user_post_dates(CH, 100) == ["2024-01-15"]
        assert await get_user_post_dates(CH2, 100) == ["2024-01-16"]

    async def test_same_day_both_channels_deduped(self):
        """Posting in both channels on the same day counts as one day."""
        from bot.db.queries import upsert_daily_participation, get_user_post_dates_cross_channel

        await upsert_daily_participation(CH, 100, "2024-01-15", 10)
        await upsert_daily_participation(CH2, 100, "2024-01-15", 20)

        dates = await get_user_post_dates_cross_channel(100)
        assert dates == ["2024-01-15"]

    async def test_missing_today_cross_channel(self):
        """Posting in another channel today means not missing in this channel."""
        from bot.db.queries import upsert_member, upsert_daily_participation, get_missing_today

        await upsert_member(CH, 100, "alice", "Alice")
        # Alice only posted in CH2, not in CH
        await upsert_daily_participation(CH2, 100, "2024-01-15", 10)

        missing = await get_missing_today(CH, "2024-01-15")
        # Alice should NOT be missing — she posted in the other channel
        assert not any(m["user_id"] == 100 for m in missing)

    async def test_missing_today_no_posts_anywhere(self):
        """Member who posted nowhere is still missing."""
        from bot.db.queries import upsert_member, get_missing_today

        await upsert_member(CH, 100, "alice", "Alice")

        missing = await get_missing_today(CH, "2024-01-15")
        assert any(m["user_id"] == 100 for m in missing)

    async def test_compliance_snapshot_cross_channel_last_post(self):
        """Compliance snapshot uses the latest post date across all channels."""
        from bot.db.queries import (
            activate_member, upsert_daily_participation, get_member_compliance_snapshots,
        )
        from datetime import datetime
        from zoneinfo import ZoneInfo

        await activate_member(CH, 100, "alice", "Alice", source="test",
                              joined_at=datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")))
        # Post in CH on day 10, post in CH2 on day 15
        await upsert_daily_participation(CH, 100, "2024-01-10", 10)
        await upsert_daily_participation(CH2, 100, "2024-01-15", 20)

        snapshots = await get_member_compliance_snapshots(CH)
        alice = next(s for s in snapshots if s["user_id"] == 100)
        # Should see the latest date across channels
        assert alice["last_post_date"] == "2024-01-15"

    async def test_get_user_channel_ids(self):
        """get_user_channel_ids returns all channels where user is active."""
        from bot.db.queries import activate_member, get_user_channel_ids
        from datetime import datetime
        from zoneinfo import ZoneInfo

        joined = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
        await activate_member(CH, 100, "alice", "Alice", source="test", joined_at=joined)
        await activate_member(CH2, 100, "alice", "Alice", source="test", joined_at=joined)

        channel_ids = await get_user_channel_ids(100)
        assert sorted(channel_ids) == sorted([CH, CH2])

    async def test_reset_progress_only_affects_one_channel(self):
        """Resetting progress in one channel doesn't touch the other."""
        from bot.db.queries import (
            activate_member, upsert_daily_participation,
            get_user_post_dates, mark_member_status,
        )
        from datetime import datetime
        from zoneinfo import ZoneInfo

        joined = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
        await activate_member(CH, 100, "alice", "Alice", source="test", joined_at=joined)
        await activate_member(CH2, 100, "alice", "Alice", source="test", joined_at=joined)
        await upsert_daily_participation(CH, 100, "2024-01-15", 10)
        await upsert_daily_participation(CH2, 100, "2024-01-15", 20)

        # Kick from CH and rejoin — only CH progress should reset
        await mark_member_status(CH, 100, "kicked", source="test")
        await activate_member(CH, 100, "alice", "Alice", source="rejoin", joined_at=joined)

        assert await get_user_post_dates(CH, 100) == []
        assert await get_user_post_dates(CH2, 100) == ["2024-01-15"]
