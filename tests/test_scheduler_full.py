"""Integration tests for scheduler — evening warnings and midnight enforcement with real DB."""

from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from bot.db import queries
from bot.services.scheduler import (
    _send_evening_warning,
    _run_midnight_enforcement,
    _kick_member,
    _state_key,
    STATE_LAST_WARNING_DATE,
    STATE_LAST_KICK_DATE,
)
from tests.conftest import make_bot, TEST_CHANNEL, TEST_CHANNEL_ID

CH = TEST_CHANNEL_ID


class TestSendEveningWarning:
    async def test_no_missing_members(self):
        """When everyone has written, no warning is sent."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test",
                                      joined_at=datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")))
        await queries.upsert_daily_participation(CH, 100, "2024-01-15", 50)
        await queries.update_streak(CH, 100, "alice", "Alice", 1, 1, "2024-01-15")

        bot = make_bot()
        await _send_evening_warning(bot, TEST_CHANNEL, "2024-01-15")

        bot.send_message.assert_not_called()
        key = _state_key(TEST_CHANNEL.slug, STATE_LAST_WARNING_DATE)
        assert await queries.get_state(key) == "2024-01-15"

    async def test_missing_members_warned(self):
        """Members who haven't written today should get a warning."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test",
                                      joined_at=datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")))
        await queries.activate_member(CH, 200, "bob", "Bob", source="test",
                                      joined_at=datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")))
        await queries.upsert_daily_participation(CH, 100, "2024-01-15", 50)
        await queries.update_streak(CH, 100, "alice", "Alice", 1, 1, "2024-01-15")

        bot = make_bot()
        await _send_evening_warning(bot, TEST_CHANNEL, "2024-01-15")

        bot.send_message.assert_called_once()
        text = bot.send_message.call_args[1].get("text") or bot.send_message.call_args[0][1]
        assert "bob" in text.lower()

    async def test_kick_warning_included_for_overdue_members(self):
        """Members overdue for 2+ days should get kick warning in addition to missing warning."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test",
                                      joined_at=datetime(2024, 1, 10, tzinfo=ZoneInfo("UTC")))
        await queries.update_streak(CH, 100, "alice", "Alice", 0, 1, "2024-01-12")

        bot = make_bot()
        await _send_evening_warning(bot, TEST_CHANNEL, "2024-01-15")

        bot.send_message.assert_called_once()
        text = bot.send_message.call_args[1].get("text") or bot.send_message.call_args[0][1]
        assert "удалит" in text


class TestKickMember:
    async def test_successful_kick(self):
        await queries.activate_member(CH, 100, "alice", "Alice", source="test")

        bot = make_bot()
        result = await _kick_member(bot, TEST_CHANNEL, {"user_id": 100})

        assert result is True
        bot.ban_chat_member.assert_called()
        bot.unban_chat_member.assert_called()
        member = await queries.get_member(CH, 100)
        assert member["status"] == "kicked"

    async def test_kick_channel_fails(self):
        await queries.activate_member(CH, 100, "alice", "Alice", source="test")

        bot = make_bot()
        bot.ban_chat_member = AsyncMock(side_effect=Exception("No permission"))

        result = await _kick_member(bot, TEST_CHANNEL, {"user_id": 100})

        assert result is False


class TestRunMidnightEnforcement:
    async def test_kicks_overdue_members(self):
        """Members with 2+ days without posts should be kicked."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test",
                                      joined_at=datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")))
        await queries.set_state(
            _state_key(TEST_CHANNEL.slug, "main_join_request_invite_link"),
            "https://t.me/+test",
        )

        bot = make_bot()
        await _run_midnight_enforcement(bot, TEST_CHANNEL, "2024-01-15")

        member = await queries.get_member(CH, 100)
        assert member["status"] == "kicked"
        bot.send_message.assert_called_once()
        key = _state_key(TEST_CHANNEL.slug, STATE_LAST_KICK_DATE)
        assert await queries.get_state(key) == "2024-01-15"

    async def test_no_kicks_when_all_active(self):
        """When all members posted recently, no one is kicked."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test",
                                      joined_at=datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")))
        await queries.update_streak(CH, 100, "alice", "Alice", 1, 1, "2024-01-15")

        bot = make_bot()
        await _run_midnight_enforcement(bot, TEST_CHANNEL, "2024-01-15")

        member = await queries.get_member(CH, 100)
        assert member["status"] == "active"
        bot.send_message.assert_not_called()
        key = _state_key(TEST_CHANNEL.slug, STATE_LAST_KICK_DATE)
        assert await queries.get_state(key) == "2024-01-15"

    async def test_new_member_grace_period(self):
        """Members who joined recently should not be kicked."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test",
                                      joined_at=datetime(2024, 1, 15, tzinfo=ZoneInfo("UTC")))

        bot = make_bot()
        await _run_midnight_enforcement(bot, TEST_CHANNEL, "2024-01-15")

        member = await queries.get_member(CH, 100)
        assert member["status"] == "active"
