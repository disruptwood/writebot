import html
import logging
from datetime import UTC, datetime

from aiogram import Bot, types

from bot import config
from bot.config import ChannelConfig
from bot.db import queries

logger = logging.getLogger(__name__)

ACTIVE_MEMBER_STATUSES = {"member", "administrator", "creator"}


def _state_key_invite_link(slug: str) -> str:
    return f"{slug}:main_join_request_invite_link"


def format_member_name(
    username: str | None,
    first_name: str | None,
    last_name: str | None = None,
    user_id: int | None = None,
) -> str:
    if username:
        return f"@{username}"

    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if full_name:
        return full_name
    if user_id is not None:
        return f"id:{user_id}"
    return "участник"


def format_user_mention_html(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None = None,
) -> str:
    label = format_member_name(username, first_name, last_name, user_id)
    if username:
        return html.escape(label)
    return f'<a href="tg://user?id={user_id}">{html.escape(label)}</a>'


async def ensure_main_invite_link(bot: Bot, channel_cfg: ChannelConfig) -> str:
    state_key = _state_key_invite_link(channel_cfg.slug)
    existing = await queries.get_state(state_key)
    if existing:
        return existing

    invite = await bot.create_chat_invite_link(
        channel_cfg.channel_id,
        creates_join_request=True,
        name=channel_cfg.invite_link_name,
    )
    await queries.set_state(state_key, invite.invite_link)
    logger.info("Created main join-request invite link for channel %s", channel_cfg.channel_id)
    return invite.invite_link


async def promote_channel_member(bot: Bot, channel_id: int, user_id: int, source: str) -> bool:
    try:
        await bot.promote_chat_member(
            channel_id,
            user_id,
            is_anonymous=False,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_post_stories=False,
            can_edit_stories=False,
            can_delete_stories=False,
            can_post_messages=True,
            can_edit_messages=True,
            can_pin_messages=False,
            can_manage_topics=False,
            can_manage_direct_messages=False,
            can_manage_tags=False,
        )
    except Exception:
        logger.exception("Failed to promote member %s in channel %s", user_id, channel_id)
        return False

    await queries.set_member_channel_admin(channel_id, user_id, True, source=source)
    return True


async def sync_member_from_chat(bot: Bot, channel_id: int, user_id: int, source: str) -> bool:
    try:
        chat_member = await bot.get_chat_member(channel_id, user_id)
    except Exception:
        logger.exception("Failed to fetch chat member %s for sync", user_id)
        return False

    user = chat_member.user
    status = chat_member.status
    if status not in ACTIVE_MEMBER_STATUSES:
        logger.info("User %s is not active in channel during sync: %s", user_id, status)
        return False

    await queries.activate_member(
        channel_id=channel_id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        source=source,
    )

    if status == "administrator":
        await queries.set_member_channel_admin(channel_id, user.id, True, source=f"{source}_already_admin")
        return True

    return await promote_channel_member(bot, channel_id, user.id, source=f"{source}_promotion")


async def activate_and_promote_member(
    bot: Bot,
    channel_id: int,
    user: types.User,
    source: str,
    joined_at: datetime | None = None,
) -> bool:
    joined_at = joined_at or datetime.now(UTC)
    await queries.activate_member(
        channel_id=channel_id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        joined_at=joined_at,
        source=source,
    )
    return await promote_channel_member(bot, channel_id, user.id, source=f"{source}_promotion")
