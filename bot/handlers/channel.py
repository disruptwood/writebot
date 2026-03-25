"""Handler for channel_post updates — tracks who writes in the channel."""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from aiogram import Router, types

from bot.config import TIMEZONE, get_channel_by_channel_id
from bot.db import queries
from bot.services.streaks import calculate_streak

logger = logging.getLogger(__name__)
router = Router()


def _get_local_date() -> str:
    """Get today's date in the configured timezone as ISO string."""
    return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()


async def _resolve_post_author(channel_id: int, message: types.Message) -> tuple[dict | None, str | None]:
    user = message.from_user
    if user and not user.is_bot:
        return {
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }, "from_user"

    author_signature = message.author_signature
    if author_signature:
        matches = await queries.find_members_by_author_signature(channel_id, author_signature)
        if len(matches) == 1:
            return matches[0], "author_signature"
        if len(matches) > 1:
            logger.warning(
                "Ambiguous author_signature for channel post: %r -> %s matches",
                author_signature,
                len(matches),
            )

    return None, None


@router.channel_post()
async def on_channel_post(message: types.Message):
    """Track every post in a monitored channel."""
    if not message.chat:
        return

    channel_cfg = get_channel_by_channel_id(message.chat.id)
    if not channel_cfg:
        return

    channel_id = channel_cfg.channel_id
    author_signature = message.author_signature
    char_count = len(message.text or message.caption or "")
    now = datetime.now(UTC)
    today = _get_local_date()
    resolved_user, resolved_via = await _resolve_post_author(channel_id, message)

    if not resolved_user:
        logger.warning(
            "Channel post WITHOUT resolved user: message_id=%s, "
            "author_signature=%r, sender_chat=%s, chars=%d",
            message.message_id,
            author_signature,
            message.sender_chat.id if message.sender_chat else None,
            char_count,
        )
        await queries.record_post(
            channel_id=channel_id,
            message_id=message.message_id,
            user_id=None,
            username=None,
            first_name=None,
            author_signature=author_signature,
            posted_at=now,
            char_count=char_count,
        )
        return

    user_id = resolved_user["user_id"]
    username = resolved_user.get("username")
    first_name = resolved_user.get("first_name")
    last_name = resolved_user.get("last_name")

    await queries.record_post(
        channel_id=channel_id,
        message_id=message.message_id,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        author_signature=author_signature,
        posted_at=now,
        char_count=char_count,
        resolved_via=resolved_via,
    )

    await queries.upsert_daily_participation(channel_id, user_id, today, char_count)
    await queries.upsert_member(channel_id, user_id, username, first_name, last_name)

    # Cross-channel streak: count posts from ALL channels
    post_dates = await queries.get_user_post_dates_cross_channel(user_id)
    current, longest = calculate_streak(post_dates, today)
    await queries.update_streak(channel_id, user_id, username, first_name, current, longest, today)

    # Update streak in other channels the user belongs to
    other_channel_ids = await queries.get_user_channel_ids(user_id)
    for other_ch in other_channel_ids:
        if other_ch != channel_id:
            await queries.update_streak(other_ch, user_id, username, first_name, current, longest, today)

    logger.info(
        "Tracked post from %s (user_id=%s), streak=%d, date=%s, resolved_via=%s, channel=%s",
        username or first_name,
        user_id,
        current,
        today,
        resolved_via,
        channel_cfg.slug,
    )
