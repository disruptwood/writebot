"""Background scheduler for evening warnings, midnight kicks, and startup sync."""

import asyncio
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.enums import ParseMode

from bot import config
from bot.db import queries
from bot.services.channel_members import (
    ensure_main_invite_link,
    format_user_mention_html,
    sync_member_from_chat,
)
from bot.services.enforcement import (
    split_evening_warning_members,
    select_midnight_kick_members,
)

logger = logging.getLogger(__name__)

STATE_LAST_WARNING_DATE = "last_evening_warning_date"
STATE_LAST_KICK_DATE = "last_midnight_enforcement_date"


def _local_now():
    from datetime import datetime

    return datetime.now(ZoneInfo(config.TIMEZONE))


def _join_mentions(members: list[dict]) -> str:
    lines = []
    for member in members:
        lines.append(
            format_user_mention_html(
                member["user_id"],
                member.get("username"),
                member.get("first_name"),
                member.get("last_name"),
            )
        )
    return "\n".join(lines)


async def _startup_sync(bot: Bot):
    await ensure_main_invite_link(bot)

    for user_id in config.MANUAL_MEMBER_IDS:
        await sync_member_from_chat(bot, user_id, source="manual_bootstrap")


async def _retry_member_sync(bot: Bot):
    for member in await queries.get_pending_members():
        await sync_member_from_chat(bot, member["user_id"], source="pending_retry")

    for member in await queries.get_members_pending_promotion():
        await sync_member_from_chat(bot, member["user_id"], source="promotion_retry")


async def _send_evening_warning(bot: Bot, evaluation_date: str):
    snapshots = await queries.get_member_compliance_snapshots()
    missing, due_for_kick = split_evening_warning_members(snapshots, evaluation_date)

    if not missing:
        logger.info("No missing writers for %s evening warning", evaluation_date)
        await queries.set_state(STATE_LAST_WARNING_DATE, evaluation_date)
        return

    sections = [
        config.STRINGS["warning_missing"].format(
            mentions=_join_mentions([member.__dict__ for member in missing])
        )
    ]
    if due_for_kick:
        sections.append(
            config.STRINGS["warning_kick_tonight"].format(
                mentions=_join_mentions([member.__dict__ for member in due_for_kick])
            )
        )

    await bot.send_message(
        config.REMINDER_CHAT_ID,
        "\n\n".join(sections),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await queries.set_state(STATE_LAST_WARNING_DATE, evaluation_date)
    logger.info("Sent evening warning for %s", evaluation_date)


async def _kick_member(bot: Bot, member: dict) -> bool:
    user_id = member["user_id"]

    try:
        await bot.ban_chat_member(config.CHANNEL_ID, user_id)
        await bot.unban_chat_member(config.CHANNEL_ID, user_id, only_if_banned=True)
    except Exception:
        logger.exception("Failed to remove user %s from channel", user_id)
        return False

    try:
        await bot.ban_chat_member(config.DISCUSSION_GROUP_ID, user_id)
        await bot.unban_chat_member(
            config.DISCUSSION_GROUP_ID,
            user_id,
            only_if_banned=True,
        )
    except Exception:
        logger.exception("Failed to remove user %s from discussion group", user_id)

    await queries.mark_member_status(
        user_id,
        "kicked",
        source="midnight_enforcement",
    )
    return True


async def _run_midnight_enforcement(bot: Bot, evaluation_date: str):
    snapshots = await queries.get_member_compliance_snapshots()
    due_for_kick = select_midnight_kick_members(snapshots, evaluation_date)

    kicked = []
    for member in due_for_kick:
        member_dict = member.__dict__
        if await _kick_member(bot, member_dict):
            kicked.append(member_dict)

    if kicked:
        invite_link = await ensure_main_invite_link(bot)
        text = config.STRINGS["kicked_for_inactivity"].format(
            mentions=_join_mentions(kicked)
        )
        text = f"{text}\n\n{config.STRINGS['invite_link'].format(invite_link=invite_link)}"
        await bot.send_message(
            config.REMINDER_CHAT_ID,
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("Kicked %s inactive members for %s", len(kicked), evaluation_date)
    else:
        logger.info("No midnight kicks required for %s", evaluation_date)

    await queries.set_state(STATE_LAST_KICK_DATE, evaluation_date)


async def _run_due_jobs(bot: Bot):
    now = _local_now()
    today = now.date().isoformat()
    warning_cutoff = (
        config.EVENING_WARNING_HOUR,
        config.EVENING_WARNING_MINUTE,
    )
    if (now.hour, now.minute) >= warning_cutoff:
        if await queries.get_state(STATE_LAST_WARNING_DATE) != today:
            await _send_evening_warning(bot, today)

    yesterday = (now.date() - timedelta(days=1)).isoformat()
    if await queries.get_state(STATE_LAST_KICK_DATE) != yesterday:
        await _run_midnight_enforcement(bot, yesterday)

    await _retry_member_sync(bot)


async def start_scheduler(bot: Bot):
    logger.info(
        "Scheduler started for %02d:%02d warning and %02d:%02d enforcement in %s",
        config.EVENING_WARNING_HOUR,
        config.EVENING_WARNING_MINUTE,
        config.MIDNIGHT_ENFORCEMENT_HOUR,
        config.MIDNIGHT_ENFORCEMENT_MINUTE,
        config.TIMEZONE,
    )

    await _startup_sync(bot)

    while True:
        try:
            await _run_due_jobs(bot)
        except Exception:
            logger.exception("Scheduler error")

        await asyncio.sleep(30)
