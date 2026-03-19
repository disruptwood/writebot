"""Private chat handlers — /start and /mystats."""

from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command

from bot.config import STRINGS
from bot.db import queries

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(STRINGS["welcome"])


@router.message(Command("mystats"))
async def cmd_mystats(message: types.Message):
    """Show personal streak in DM."""
    if not message.from_user:
        return

    streak = await queries.get_streak(message.from_user.id)
    name = message.from_user.first_name or "Аноним"

    if not streak or streak["current_streak"] == 0:
        await message.answer(STRINGS["no_streak"].format(name=name))
        return

    await message.answer(STRINGS["streak"].format(
        name=name,
        current=streak["current_streak"],
        longest=streak["longest_streak"],
    ))
