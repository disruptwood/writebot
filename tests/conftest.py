"""Shared fixtures for WriteBot tests.

Provides:
- Temporary DB setup (auto-used)
- Telegram mock factories for Message, User, Chat, Bot, etc.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

# Ensure bot package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override config before importing bot modules
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("CHANNEL_ID", "-1001234567890")
os.environ.setdefault("DISCUSSION_GROUP_ID", "-1009876543210")

from bot import config  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a temp file DB for each test."""
    config.DB_PATH = str(tmp_path / "test.db")
    from bot.db.models import init_db
    await init_db()
    yield


# ── Telegram Mock Factories ──


def make_user(
    user_id: int = 100,
    username: str | None = "testuser",
    first_name: str = "Test",
    last_name: str | None = None,
    is_bot: bool = False,
) -> SimpleNamespace:
    """Create a mock Telegram User."""
    return SimpleNamespace(
        id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        is_bot=is_bot,
    )


def make_chat(
    chat_id: int = config.CHANNEL_ID,
    chat_type: str = "channel",
    title: str = "Test Channel",
) -> SimpleNamespace:
    """Create a mock Telegram Chat."""
    return SimpleNamespace(
        id=chat_id,
        type=chat_type,
        title=title,
    )


def make_message(
    message_id: int = 1,
    text: str = "Hello world",
    chat: SimpleNamespace | None = None,
    from_user: SimpleNamespace | None = None,
    reply_to_message: object | None = None,
    author_signature: str | None = None,
    sender_chat: SimpleNamespace | None = None,
    caption: str | None = None,
) -> MagicMock:
    """Create a mock Telegram Message with async answer()."""
    msg = MagicMock()
    msg.message_id = message_id
    msg.text = text
    msg.caption = caption
    msg.chat = chat or make_chat()
    msg.from_user = from_user
    msg.reply_to_message = reply_to_message
    msg.author_signature = author_signature
    msg.sender_chat = sender_chat
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    return msg


def make_bot() -> MagicMock:
    """Create a mock Telegram Bot with common async methods."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.get_chat = AsyncMock()
    bot.get_me = AsyncMock(return_value=make_user(user_id=999, username="testbot", is_bot=True))
    bot.get_chat_member = AsyncMock()
    bot.ban_chat_member = AsyncMock()
    bot.unban_chat_member = AsyncMock()
    bot.promote_chat_member = AsyncMock()
    bot.create_chat_invite_link = AsyncMock()
    return bot


def make_join_request(
    chat_id: int = config.CHANNEL_ID,
    user: SimpleNamespace | None = None,
) -> SimpleNamespace:
    """Create a mock ChatJoinRequest."""
    return SimpleNamespace(
        chat=make_chat(chat_id=chat_id),
        from_user=user or make_user(),
    )


def make_chat_member_updated(
    chat_id: int = config.CHANNEL_ID,
    user: SimpleNamespace | None = None,
    old_status: str = "left",
    new_status: str = "member",
) -> SimpleNamespace:
    """Create a mock ChatMemberUpdated."""
    from datetime import datetime, UTC
    u = user or make_user()
    return SimpleNamespace(
        chat=make_chat(chat_id=chat_id),
        old_chat_member=SimpleNamespace(status=old_status, user=u),
        new_chat_member=SimpleNamespace(status=new_status, user=u),
        date=datetime.now(UTC),
    )
