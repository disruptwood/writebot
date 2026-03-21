"""Tests for channel_members service — formatting, invite links, promotion."""

from unittest.mock import AsyncMock

from bot.db import queries
from bot.services.channel_members import (
    format_member_name,
    format_user_mention_html,
    ensure_main_invite_link,
    promote_channel_member,
    sync_member_from_chat,
    activate_and_promote_member,
)
from tests.conftest import make_bot, make_user


class TestFormatMemberName:
    def test_with_username(self):
        assert format_member_name("alice", "Alice") == "@alice"

    def test_with_first_name_only(self):
        assert format_member_name(None, "Alice") == "Alice"

    def test_with_full_name(self):
        assert format_member_name(None, "Alice", "Smith") == "Alice Smith"

    def test_with_user_id_only(self):
        assert format_member_name(None, None, None, 42) == "id:42"

    def test_fallback(self):
        assert format_member_name(None, None) == "участник"


class TestFormatUserMentionHtml:
    def test_with_username_escapes(self):
        result = format_user_mention_html(100, "alice", "Alice")
        assert result == "@alice"

    def test_without_username_creates_link(self):
        result = format_user_mention_html(100, None, "Alice")
        assert 'href="tg://user?id=100"' in result
        assert "Alice" in result

    def test_html_escaping(self):
        result = format_user_mention_html(100, None, "Alice<script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestEnsureMainInviteLink:
    async def test_creates_new_link(self):
        bot = make_bot()
        invite_obj = type("Invite", (), {"invite_link": "https://t.me/+new123"})()
        bot.create_chat_invite_link = AsyncMock(return_value=invite_obj)

        link = await ensure_main_invite_link(bot)

        assert link == "https://t.me/+new123"
        bot.create_chat_invite_link.assert_called_once()

    async def test_returns_cached_link(self):
        await queries.set_state("main_join_request_invite_link", "https://t.me/+cached")

        bot = make_bot()
        link = await ensure_main_invite_link(bot)

        assert link == "https://t.me/+cached"
        bot.create_chat_invite_link.assert_not_called()


class TestPromoteChannelMember:
    async def test_successful_promotion(self):
        await queries.activate_member(100, "alice", "Alice", source="test")

        bot = make_bot()
        result = await promote_channel_member(bot, 100, source="test")

        assert result is True
        bot.promote_chat_member.assert_called_once()
        member = await queries.get_member(100)
        assert member["is_channel_admin"] == 1

    async def test_failed_promotion(self):
        await queries.activate_member(100, "alice", "Alice", source="test")

        bot = make_bot()
        bot.promote_chat_member = AsyncMock(side_effect=Exception("API error"))

        result = await promote_channel_member(bot, 100, source="test")

        assert result is False
        member = await queries.get_member(100)
        assert member["is_channel_admin"] == 0


class TestSyncMemberFromChat:
    async def test_active_member_synced_and_promoted(self):
        bot = make_bot()
        chat_member = type("CM", (), {
            "user": make_user(user_id=100, username="alice", first_name="Alice"),
            "status": "member",
        })()
        bot.get_chat_member = AsyncMock(return_value=chat_member)

        result = await sync_member_from_chat(bot, 100, source="test")

        assert result is True
        member = await queries.get_member(100)
        assert member is not None
        assert member["is_active"] == 1

    async def test_non_active_member_not_synced(self):
        bot = make_bot()
        chat_member = type("CM", (), {
            "user": make_user(user_id=100),
            "status": "left",
        })()
        bot.get_chat_member = AsyncMock(return_value=chat_member)

        result = await sync_member_from_chat(bot, 100, source="test")

        assert result is False

    async def test_api_error_returns_false(self):
        bot = make_bot()
        bot.get_chat_member = AsyncMock(side_effect=Exception("Network error"))

        result = await sync_member_from_chat(bot, 100, source="test")

        assert result is False

    async def test_already_admin_skips_promotion(self):
        bot = make_bot()
        chat_member = type("CM", (), {
            "user": make_user(user_id=100, username="alice", first_name="Alice"),
            "status": "administrator",
        })()
        bot.get_chat_member = AsyncMock(return_value=chat_member)

        result = await sync_member_from_chat(bot, 100, source="test")

        assert result is True
        bot.promote_chat_member.assert_not_called()
        member = await queries.get_member(100)
        assert member["is_channel_admin"] == 1


class TestActivateAndPromoteMember:
    async def test_activates_and_promotes(self):
        bot = make_bot()
        user = make_user(user_id=100, username="alice", first_name="Alice")

        result = await activate_and_promote_member(bot, user, source="test")

        assert result is True
        member = await queries.get_member(100)
        assert member["is_active"] == 1
        assert member["is_channel_admin"] == 1
