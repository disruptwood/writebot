"""Background scheduler for daily summary messages.

Runs after midnight (Israel time) to summarize the previous day.
Persists last summary date in DB to avoid double-posting on restart.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.config import DISCUSSION_GROUP_ID, TIMEZONE, DAILY_SUMMARY_HOUR, STRINGS
from bot.db import queries

logger = logging.getLogger(__name__)

# Key for tracking last summary in bot_state table
STATE_LAST_SUMMARY = "last_summary_date"


def _seconds_until(hour: int, minute: int, tz: str) -> float:
    """Seconds until next occurrence of the given hour:minute in the given timezone."""
    now = datetime.now(ZoneInfo(tz))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _post_daily_summary(bot: Bot):
    """Compose and send the daily summary to the discussion group.

    Summarizes the PREVIOUS day (since we run after midnight).
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)

    # If running shortly after midnight, summarize yesterday
    # If DAILY_SUMMARY_HOUR < 12 (morning), summarize yesterday
    # If DAILY_SUMMARY_HOUR >= 12 (evening), summarize today
    if DAILY_SUMMARY_HOUR < 12:
        summary_date = (now - timedelta(days=1)).date().isoformat()
    else:
        summary_date = now.date().isoformat()

    # Check if we already posted for this date
    last_summary = await queries.get_state(STATE_LAST_SUMMARY)
    if last_summary == summary_date:
        logger.info("Summary for %s already posted, skipping", summary_date)
        return

    writers = await queries.get_today_writers(summary_date)
    members = await queries.get_active_members()
    leaders = await queries.get_leaderboard(limit=3)

    streak_lines = []
    for s in leaders:
        name = f"@{s['username']}" if s.get("username") else (s.get("first_name") or "?")
        streak_lines.append(f"  🔥 {name} — {s['current_streak']} дн.")

    streak_info = "\n".join(streak_lines) if streak_lines else "  Стриков пока нет."

    text = STRINGS["daily_summary"].format(
        date=summary_date,
        count=len(writers),
        total=len(members),
        streak_info=streak_info,
    )

    try:
        await bot.send_message(DISCUSSION_GROUP_ID, text)
        await queries.set_state(STATE_LAST_SUMMARY, summary_date)
        logger.info("Daily summary posted for %s", summary_date)
    except Exception as e:
        logger.error("Failed to post daily summary: %s", e)


async def start_scheduler(bot: Bot):
    """Run the daily summary loop. Call as a background asyncio task."""
    logger.info(
        "Scheduler started, summary at %02d:00 %s",
        DAILY_SUMMARY_HOUR, TIMEZONE,
    )

    while True:
        wait = _seconds_until(DAILY_SUMMARY_HOUR, 5, TIMEZONE)  # :05 to avoid exact-midnight edge
        logger.info("Next daily summary in %.0f seconds", wait)
        await asyncio.sleep(wait)

        try:
            await _post_daily_summary(bot)
        except Exception as e:
            logger.error("Scheduler error: %s", e)

        # Sleep to avoid double-firing within the same minute
        await asyncio.sleep(120)
