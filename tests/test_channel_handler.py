"""Tests for channel post handler — tracks posts and updates streaks."""


from bot import config
from bot.db import queries
from bot.handlers.channel import on_channel_post, _resolve_post_author
from tests.conftest import make_message, make_user, make_chat, TEST_CHANNEL_ID

CH = TEST_CHANNEL_ID


class TestOnChannelPost:
    """Tests for on_channel_post handler."""

    async def test_post_from_known_user_tracked(self):
        """A normal user post should be recorded in DB with streak update."""
        user = make_user(user_id=100, username="alice", first_name="Alice")
        msg = make_message(
            message_id=1,
            text="My daily writing post",
            chat=make_chat(chat_id=CH),
            from_user=user,
        )

        await on_channel_post(msg)

        dates = await queries.get_user_post_dates(CH, 100)
        assert len(dates) == 1

        streak = await queries.get_streak(CH, 100)
        assert streak is not None
        assert streak["current_streak"] >= 1

        member = await queries.get_member(CH, 100)
        assert member is not None
        assert member["username"] == "alice"

    async def test_post_without_user_recorded_as_anonymous(self):
        """A post without from_user (channel identity) should still be saved."""
        msg = make_message(
            message_id=2,
            text="Anonymous post",
            chat=make_chat(chat_id=CH),
            from_user=None,
            author_signature=None,
        )

        await on_channel_post(msg)

        dates = await queries.get_user_post_dates(CH, 0)
        assert dates == []

    async def test_post_from_wrong_channel_ignored(self):
        """Posts from other channels should be ignored."""
        user = make_user(user_id=100)
        msg = make_message(
            message_id=3,
            text="Wrong channel post",
            chat=make_chat(chat_id=-999),
            from_user=user,
        )

        await on_channel_post(msg)

        dates = await queries.get_user_post_dates(CH, 100)
        assert dates == []

    async def test_post_from_bot_user_treated_as_anonymous(self):
        """Posts from bot users should be treated as anonymous."""
        bot_user = make_user(user_id=777, is_bot=True)
        msg = make_message(
            message_id=4,
            text="Bot post",
            chat=make_chat(chat_id=CH),
            from_user=bot_user,
        )

        await on_channel_post(msg)

        dates = await queries.get_user_post_dates(CH, 777)
        assert dates == []

    async def test_multiple_posts_same_day_aggregate(self):
        """Multiple posts same day should aggregate in participation."""
        user = make_user(user_id=100, username="alice", first_name="Alice")
        for i in range(3):
            msg = make_message(
                message_id=10 + i,
                text=f"Post #{i}",
                chat=make_chat(chat_id=CH),
                from_user=user,
            )
            await on_channel_post(msg)

        dates = await queries.get_user_post_dates(CH, 100)
        assert len(dates) == 1  # Same day

        streak = await queries.get_streak(CH, 100)
        assert streak["current_streak"] == 1

    async def test_caption_counted_for_media_posts(self):
        """For media posts, caption length should be counted."""
        user = make_user(user_id=100, username="alice", first_name="Alice")
        msg = make_message(
            message_id=5,
            text=None,
            caption="Photo caption text",
            chat=make_chat(chat_id=CH),
            from_user=user,
        )

        await on_channel_post(msg)

        dates = await queries.get_user_post_dates(CH, 100)
        assert len(dates) == 1

    async def test_post_with_no_chat_ignored(self):
        """Messages without chat should be ignored."""
        msg = make_message(message_id=6, text="No chat")
        msg.chat = None

        await on_channel_post(msg)


class TestResolvePostAuthor:
    """Tests for _resolve_post_author helper."""

    async def test_resolves_from_user(self):
        """Normal user should be resolved via from_user."""
        user = make_user(user_id=100, username="alice", first_name="Alice", last_name="Smith")
        msg = make_message(from_user=user)

        result, method = await _resolve_post_author(CH, msg)

        assert result is not None
        assert result["user_id"] == 100
        assert result["username"] == "alice"
        assert result["last_name"] == "Smith"
        assert method == "from_user"

    async def test_resolves_via_author_signature_unique_match(self):
        """When author_signature matches exactly one member, resolve to them."""
        await queries.activate_member(CH, 100, "alice", "Alice", "Smith", source="test")

        msg = make_message(from_user=None, author_signature="Alice Smith")

        result, method = await _resolve_post_author(CH, msg)

        assert result is not None
        assert result["user_id"] == 100
        assert method == "author_signature"

    async def test_ambiguous_signature_returns_none(self):
        """When signature matches multiple members, return None."""
        await queries.activate_member(CH, 100, None, "Alice", "Smith", source="test")
        await queries.activate_member(CH, 200, None, "Alice", "Smith", source="test")

        msg = make_message(from_user=None, author_signature="Alice Smith")

        result, method = await _resolve_post_author(CH, msg)

        assert result is None
        assert method is None

    async def test_no_signature_no_user_returns_none(self):
        """No from_user and no author_signature returns None."""
        msg = make_message(from_user=None, author_signature=None)

        result, method = await _resolve_post_author(CH, msg)

        assert result is None
        assert method is None

    async def test_bot_user_falls_through_to_signature(self):
        """Bot user should not be resolved via from_user."""
        bot_user = make_user(user_id=777, is_bot=True)
        msg = make_message(from_user=bot_user, author_signature=None)

        result, method = await _resolve_post_author(CH, msg)

        assert result is None
        assert method is None
