"""Tests for membership lifecycle handlers (join requests, member status changes)."""


from bot.db import queries
from bot.handlers.membership import on_chat_join_request, on_chat_member
from tests.conftest import (
    make_bot,
    make_chat_member_updated,
    make_join_request,
    make_user,
    TEST_CHANNEL_ID,
)

CH = TEST_CHANNEL_ID


class TestOnChatJoinRequest:
    async def test_join_request_recorded_as_pending(self):
        join_request = make_join_request(
            user=make_user(user_id=100, username="alice", first_name="Alice", last_name="Writer"),
        )

        await on_chat_join_request(join_request)

        member = await queries.get_member(CH, 100)
        assert member is not None
        assert member["status"] == "pending"
        assert member["is_active"] == 0
        assert member["is_channel_admin"] == 0

    async def test_join_request_from_wrong_channel_ignored(self):
        join_request = make_join_request(
            chat_id=-999,
            user=make_user(user_id=100),
        )

        await on_chat_join_request(join_request)

        member = await queries.get_member(CH, 100)
        assert member is None

    async def test_join_request_from_bot_ignored(self):
        join_request = make_join_request(
            user=make_user(user_id=100, is_bot=True),
        )

        await on_chat_join_request(join_request)

        member = await queries.get_member(CH, 100)
        assert member is None


class TestOnChatMember:
    async def test_member_joined_activates_and_promotes(self):
        update = make_chat_member_updated(
            user=make_user(user_id=100, username="alice", first_name="Alice"),
            old_status="left",
            new_status="member",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member is not None
        assert member["status"] == "active"
        assert member["is_active"] == 1
        bot.promote_chat_member.assert_called_once()

    async def test_member_already_admin_skips_promotion(self):
        update = make_chat_member_updated(
            user=make_user(user_id=100, username="alice", first_name="Alice"),
            old_status="left",
            new_status="administrator",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member is not None
        assert member["is_channel_admin"] == 1
        bot.promote_chat_member.assert_not_called()

    async def test_member_left_marked_inactive(self):
        await queries.activate_member(CH, 100, "alice", "Alice", source="test")

        update = make_chat_member_updated(
            user=make_user(user_id=100, username="alice", first_name="Alice"),
            old_status="member",
            new_status="left",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member["status"] == "left"
        assert member["is_active"] == 0

    async def test_member_kicked_marked(self):
        await queries.activate_member(CH, 100, "alice", "Alice", source="test")

        update = make_chat_member_updated(
            user=make_user(user_id=100, username="alice", first_name="Alice"),
            old_status="member",
            new_status="kicked",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member["status"] == "kicked"

    async def test_already_kicked_leave_ignored(self):
        """If member was already kicked by enforcement, a follow-up 'left' update shouldn't overwrite."""
        await queries.activate_member(CH, 100, "alice", "Alice", source="test")
        await queries.mark_member_status(CH, 100, "kicked", source="enforcement")

        update = make_chat_member_updated(
            user=make_user(user_id=100, username="alice", first_name="Alice"),
            old_status="member",
            new_status="left",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member["status"] == "kicked"  # Not overwritten to "left"

    async def test_wrong_channel_ignored(self):
        update = make_chat_member_updated(
            chat_id=-999,
            user=make_user(user_id=100),
            old_status="left",
            new_status="member",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member is None

    async def test_bot_user_ignored(self):
        update = make_chat_member_updated(
            user=make_user(user_id=100, is_bot=True),
            old_status="left",
            new_status="member",
        )
        bot = make_bot()

        await on_chat_member(update, bot)

        member = await queries.get_member(CH, 100)
        assert member is None
