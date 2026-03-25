"""Commands for the discussion group linked to the channel."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, types, F
from aiogram.filters import Command

from bot.config import DISCUSSION_GROUP_ID, STRINGS, TIMEZONE
from bot.db import queries

logger = logging.getLogger(__name__)
router = Router()

# Only handle messages in the discussion group
router.message.filter(F.chat.id == DISCUSSION_GROUP_ID)


def _today() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()


def _display_name(m: dict) -> str:
    if m.get("username"):
        return f"@{m['username']}"
    return m.get("first_name") or f"id:{m['user_id']}"


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Show today's writing stats."""
    today = _today()
    writers = await queries.get_today_writers(today)
    members = await queries.get_active_members()

    if not writers:
        await message.reply(STRINGS["stats_empty"])
        return

    text = STRINGS["stats"].format(today_count=len(writers), total=len(members))
    names = ", ".join(_display_name(w) for w in writers)
    await message.reply(f"{text}\n{names}")


@router.message(Command("missing"))
async def cmd_missing(message: types.Message):
    """Show who hasn't written today."""
    today = _today()
    missing = await queries.get_missing_today(today)

    if not missing:
        await message.reply("Все написали сегодня! 🎉")
        return

    names = "\n".join(f"  • {_display_name(m)}" for m in missing)
    await message.reply(f"{STRINGS['missing_header']}\n{names}")


@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    """Show streak for the requesting user."""
    if not message.from_user:
        return

    streak = await queries.get_streak(message.from_user.id)
    name = message.from_user.first_name or "Аноним"

    if not streak or streak["current_streak"] == 0:
        await message.reply(STRINGS["no_streak"].format(name=name))
        return

    await message.reply(STRINGS["streak"].format(
        name=name,
        current=streak["current_streak"],
        longest=streak["longest_streak"],
    ))


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: types.Message):
    """Show top streaks."""
    leaders = await queries.get_leaderboard(limit=10)

    if not leaders:
        await message.reply("Пока нет стриков. Начните писать!")
        return

    lines = [STRINGS["leaderboard_header"]]
    for i, s in enumerate(leaders, 1):
        name = _display_name(s)
        lines.append(f"  {i}. {name} — {s['current_streak']} дн. (рекорд: {s['longest_streak']})")

    await message.reply("\n".join(lines))
