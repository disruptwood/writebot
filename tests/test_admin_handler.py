"""Tests for admin command handlers (/addadmin, /removeadmin, /invite_link, /debug_channel)."""

from unittest.mock import AsyncMock

from bot import config
from bot.db import queries
from bot.handlers.admin import cmd_add_admin, cmd_remove_admin, cmd_invite_link, _check_admin
from tests.conftest import make_message, make_user, make_chat, make_bot


GROUP_CHAT = make_chat(
    chat_id=config.DISCUSSION_GROUP_ID,
    chat_type="supergroup",
    title="Test Discussion",
)


def _admin_message(from_user=None, reply_to_user=None, text="/addadmin"):
    reply = None
    if reply_to_user:
        reply = make_message(from_user=reply_to_user, chat=GROUP_CHAT)
    msg = make_message(
        chat=GROUP_CHAT,
        from_user=from_user or make_user(),
        text=text,
        reply_to_message=reply,
    )
    return msg


class TestCheckAdmin:
    async def test_non_admin_returns_false(self):
        user = make_user(user_id=100)
        msg = _admin_message(from_user=user)

        assert not await _check_admin(msg)

    async def test_existing_admin_returns_true(self):
        await queries.add_admin(100, "alice", "Alice", 0)
        user = make_user(user_id=100)
        msg = _admin_message(from_user=user)

        assert await _check_admin(msg)

    async def test_initial_admin_bootstrap(self, monkeypatch):
        """INITIAL_ADMIN_ID user is auto-added as admin on first check."""
        monkeypatch.setattr(config, "INITIAL_ADMIN_ID", 42)
        # Also patch the module-level import in admin handler
        from bot.handlers import admin
        monkeypatch.setattr(admin, "INITIAL_ADMIN_ID", 42)

        user = make_user(user_id=42, username="bootstrap", first_name="Boot")
        msg = _admin_message(from_user=user)

        result = await _check_admin(msg)

        assert result is True
        assert await queries.is_admin(42)

    async def test_no_from_user_returns_false(self):
        msg = _admin_message()
        msg.from_user = None

        assert not await _check_admin(msg)


class TestCmdAddAdmin:
    async def test_non_admin_rejected(self):
        user = make_user(user_id=100)
        msg = _admin_message(from_user=user)

        await cmd_add_admin(msg)

        response = msg.answer.call_args[0][0]
        assert config.STRINGS["not_admin"] == response

    async def test_no_reply_rejected(self):
        await queries.add_admin(100, "admin", "Admin", 0)
        user = make_user(user_id=100)
        msg = _admin_message(from_user=user, text="/addadmin")
        msg.reply_to_message = None

        await cmd_add_admin(msg)

        response = msg.answer.call_args[0][0]
        assert "Ответьте" in response

    async def test_add_admin_success(self):
        await queries.add_admin(100, "admin", "Admin", 0)
        admin_user = make_user(user_id=100, username="admin")
        target_user = make_user(user_id=200, username="newadmin", first_name="NewAdmin")

        msg = _admin_message(from_user=admin_user, reply_to_user=target_user)
        await cmd_add_admin(msg)

        assert await queries.is_admin(200)
        response = msg.answer.call_args[0][0]
        assert "@newadmin" in response


class TestCmdRemoveAdmin:
    async def test_remove_existing_admin(self):
        await queries.add_admin(100, "admin", "Admin", 0)
        await queries.add_admin(200, "target", "Target", 100)

        admin_user = make_user(user_id=100, username="admin")
        target_user = make_user(user_id=200, username="target", first_name="Target")

        msg = _admin_message(from_user=admin_user, reply_to_user=target_user)
        await cmd_remove_admin(msg)

        assert not await queries.is_admin(200)
        response = msg.answer.call_args[0][0]
        assert "@target" in response

    async def test_remove_non_admin(self):
        await queries.add_admin(100, "admin", "Admin", 0)

        admin_user = make_user(user_id=100, username="admin")
        target_user = make_user(user_id=300, username="nobody", first_name="Nobody")

        msg = _admin_message(from_user=admin_user, reply_to_user=target_user)
        await cmd_remove_admin(msg)

        response = msg.answer.call_args[0][0]
        assert "не является админом" in response


class TestCmdInviteLink:
    async def test_non_admin_rejected(self):
        user = make_user(user_id=100)
        msg = _admin_message(from_user=user, text="/invite_link")

        await cmd_invite_link(msg, make_bot())

        response = msg.answer.call_args[0][0]
        assert config.STRINGS["not_admin"] == response

    async def test_shows_invite_link(self):
        await queries.add_admin(100, "admin", "Admin", 0)
        user = make_user(user_id=100)
        msg = _admin_message(from_user=user, text="/invite_link")

        bot = make_bot()
        invite_obj = type("Invite", (), {"invite_link": "https://t.me/+abc123"})()
        bot.create_chat_invite_link = AsyncMock(return_value=invite_obj)

        await cmd_invite_link(msg, bot)

        response = msg.answer.call_args[0][0]
        assert "https://t.me/+abc123" in response
