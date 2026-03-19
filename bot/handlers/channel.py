"""Handler for channel_post updates — tracks who writes in the channel."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, types

from bot.config import CHANNEL_ID, TIMEZONE
from bot.db import queries
from bot.services.streaks import calculate_streak

logger = logging.getLogger(__name__)
router = Router()


def _get_local_date() -> str:
    """Get today's date in the configured timezone as ISO string."""
    return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()


@router.channel_post()
async def on_channel_post(message: types.Message):
    """Track every post in the monitored channel."""
    if not message.chat or message.chat.id != CHANNEL_ID:
        return

    user = message.from_user
    author_signature = message.author_signature  # display name string, may be None
    char_count = len(message.text or message.caption or "")
    now = datetime.utcnow()
    today = _get_local_date()

    if not user:
        # Posted "as channel" — no user_id available.
        # Log everything we have so we can debug attribution.
        logger.warning(
            "Channel post WITHOUT from_user: message_id=%s, "
            "author_signature=%r, sender_chat=%s, chars=%d",
            message.message_id,
            author_signature,
            message.sender_chat.id if message.sender_chat else None,
            char_count,
        )
        # Still save the raw post for audit trail
        await queries.record_post(
            message_id=message.message_id,
            user_id=None,
            username=None,
            first_name=None,
            author_signature=author_signature,
            posted_at=now,
            char_count=char_count,
        )
        return

    user_id = user.id
    username = user.username
    first_name = user.first_name

    # Record the raw post
    await queries.record_post(
        message_id=message.message_id,
        user_id=user_id,
        username=username,
        first_name=first_name,
        author_signature=author_signature,
        posted_at=now,
        char_count=char_count,
    )

    # Update daily participation
    await queries.upsert_daily_participation(user_id, today, char_count)

    # Ensure user is in members table
    await queries.upsert_member(user_id, username, first_name)

    # Recalculate streak
    post_dates = await queries.get_user_post_dates(user_id)
    current, longest = calculate_streak(post_dates, today)
    await queries.update_streak(user_id, username, first_name, current, longest, today)

    logger.info(
        "Tracked post from %s (user_id=%s), streak=%d, date=%s",
        username or first_name, user_id, current, today,
    )
