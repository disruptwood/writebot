"""Private chat handlers — /start and /mystats."""

from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command

from bot.config import STRINGS, get_primary_channel
from bot.db import queries

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply(STRINGS["welcome"])


@router.message(Command("mystats"))
async def cmd_mystats(message: types.Message):
    """Show personal streak in DM (primary channel only)."""
    if not message.from_user:
        return

    primary = get_primary_channel()
    if not primary:
        await message.reply("Канал ещё не настроен.")
        return

    streak = await queries.get_streak(primary.channel_id, message.from_user.id)
    name = message.from_user.first_name or "Аноним"

    if not streak or streak["current_streak"] == 0:
        await message.reply(STRINGS["no_streak"].format(name=name))
        return

    await message.reply(STRINGS["streak"].format(
        name=name,
        current=streak["current_streak"],
        longest=streak["longest_streak"],
    ))
