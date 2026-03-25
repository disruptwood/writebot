"""Tests for private chat handlers (/start, /mystats)."""


from bot import config
from bot.db import queries
from bot.handlers.private import cmd_start, cmd_mystats
from tests.conftest import make_message, make_user, make_chat


PRIVATE_CHAT = make_chat(chat_id=100, chat_type="private", title="DM")


def _private_message(from_user=None, text="/start"):
    return make_message(
        chat=PRIVATE_CHAT,
        from_user=from_user or make_user(),
        text=text,
    )


class TestCmdStart:
    async def test_welcome_message(self):
        msg = _private_message()
        await cmd_start(msg)

        response = msg.reply.call_args[0][0]
        assert config.STRINGS["welcome"] == response


class TestCmdMystats:
    async def test_no_streak(self):
        user = make_user(user_id=100, first_name="Alice")
        msg = _private_message(from_user=user)

        await cmd_mystats(msg)

        response = msg.reply.call_args[0][0]
        assert "нет стрика" in response

    async def test_with_streak(self):
        user = make_user(user_id=100, first_name="Alice")
        await queries.update_streak(100, "alice", "Alice", 3, 7, "2024-01-15")

        msg = _private_message(from_user=user)
        await cmd_mystats(msg)

        response = msg.reply.call_args[0][0]
        assert "3" in response
        assert "7" in response

    async def test_no_from_user_ignored(self):
        msg = _private_message()
        msg.from_user = None

        await cmd_mystats(msg)

        msg.reply.assert_not_called()
