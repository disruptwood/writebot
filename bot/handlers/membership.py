"""Membership lifecycle handlers for channel join requests and member updates."""

import logging
from datetime import UTC

from aiogram import Bot, Router, types

from bot.config import get_channel_by_channel_id, get_channel_by_group_id
from bot.db import queries
from bot.services.channel_members import (
    ACTIVE_MEMBER_STATUSES,
    promote_channel_member,
)

logger = logging.getLogger(__name__)
router = Router()


@router.chat_join_request()
async def on_chat_join_request(join_request: types.ChatJoinRequest):
    channel_cfg = get_channel_by_channel_id(join_request.chat.id) or get_channel_by_group_id(join_request.chat.id)
    if not channel_cfg:
        return

    user = join_request.from_user
    if user.is_bot:
        return

    await queries.create_or_update_pending_member(
        channel_id=channel_cfg.channel_id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        source="chat_join_request",
    )
    logger.info("Recorded join request for user %s in %s; awaiting manual approval", user.id, channel_cfg.slug)


@router.chat_member()
async def on_chat_member(update: types.ChatMemberUpdated, bot: Bot):
    channel_cfg = get_channel_by_channel_id(update.chat.id) or get_channel_by_group_id(update.chat.id)
    if not channel_cfg:
        return

    channel_id = channel_cfg.channel_id
    user = update.new_chat_member.user
    if user.is_bot:
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    changed_at = update.date
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=UTC)

    if new_status in ACTIVE_MEMBER_STATUSES:
        await queries.activate_member(
            channel_id=channel_id,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            joined_at=changed_at,
            source="chat_member_sync",
        )

        if new_status in {"administrator", "creator"}:
            await queries.set_member_channel_admin(
                channel_id,
                user.id,
                True,
                source="chat_member_sync",
            )
        else:
            await promote_channel_member(bot, channel_id, user.id, source="chat_member_sync")
        return

    if old_status in ACTIVE_MEMBER_STATUSES and new_status in {"left", "kicked"}:
        existing = await queries.get_member(channel_id, user.id)
        if existing and existing.get("status") == "kicked":
            logger.info("Leave update confirmed previously kicked member %s", user.id)
            return

        await queries.mark_member_status(
            channel_id,
            user.id,
            "left" if new_status == "left" else "kicked",
            source="chat_member_sync",
        )
        logger.info(
            "Marked member %s inactive due to status change %s -> %s in %s",
            user.id,
            old_status,
            new_status,
            channel_cfg.slug,
        )
