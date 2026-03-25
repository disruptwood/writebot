"""Admin-only commands for managing the writing channel."""

import logging

from aiogram import Router, types, F, Bot
from aiogram.filters import Command

from bot.config import (
    ALL_GROUP_IDS,
    INITIAL_ADMIN_ID,
    STRINGS,
    get_channel_by_group_id,
)
from bot.db import queries
from bot.services.channel_members import ensure_main_invite_link

logger = logging.getLogger(__name__)
router = Router()

# Only in known discussion groups
router.message.filter(F.chat.id.in_(ALL_GROUP_IDS))


async def _check_admin(message: types.Message) -> bool:
    """Check if user is a bot admin. Bootstrap initial admin on first use."""
    if not message.from_user:
        return False
    user_id = message.from_user.id

    # Bootstrap: if INITIAL_ADMIN_ID is set and no admins exist, add them
    if INITIAL_ADMIN_ID and user_id == INITIAL_ADMIN_ID:
        if not await queries.is_admin(user_id):
            await queries.add_admin(
                user_id, message.from_user.username,
                message.from_user.first_name, user_id,
            )
            logger.info("Bootstrapped initial admin: %s", user_id)

    return await queries.is_admin(user_id)


@router.message(Command("addadmin"))
async def cmd_add_admin(message: types.Message):
    """Add a bot admin. Usage: /addadmin (reply to user's message)."""
    if not await _check_admin(message):
        await message.reply(STRINGS["not_admin"])
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Ответьте на сообщение пользователя, которого хотите сделать админом.")
        return

    target = message.reply_to_message.from_user
    await queries.add_admin(target.id, target.username, target.first_name, message.from_user.id)
    name = f"@{target.username}" if target.username else target.first_name
    await message.reply(STRINGS["admin_added"].format(name=name))


@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: types.Message):
    """Remove a bot admin. Usage: /removeadmin (reply to user's message)."""
    if not await _check_admin(message):
        await message.reply(STRINGS["not_admin"])
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Ответьте на сообщение пользователя, которого хотите убрать из админов.")
        return

    target = message.reply_to_message.from_user
    removed = await queries.remove_admin(target.id)
    name = f"@{target.username}" if target.username else target.first_name

    if removed:
        await message.reply(STRINGS["admin_removed"].format(name=name))
    else:
        await message.reply(f"{name} не является админом.")


@router.message(Command("invite_link"))
async def cmd_invite_link(message: types.Message, bot: Bot):
    """Show the bot-owned join-request invite link."""
    if not await _check_admin(message):
        await message.reply(STRINGS["not_admin"])
        return

    channel_cfg = get_channel_by_group_id(message.chat.id)
    if not channel_cfg:
        return

    invite_link = await ensure_main_invite_link(bot, channel_cfg)
    await message.reply(STRINGS["invite_link"].format(invite_link=invite_link))


@router.message(Command("debug_channel"))
async def cmd_debug_channel(message: types.Message, bot: Bot):
    """Show diagnostic info about channel/group setup. Admin only."""
    if not await _check_admin(message):
        await message.reply(STRINGS["not_admin"])
        return

    channel_cfg = get_channel_by_group_id(message.chat.id)
    if not channel_cfg:
        return

    lines = [
        f"Channel: {channel_cfg.name} ({channel_cfg.slug})",
        f"CHANNEL_ID: {channel_cfg.channel_id}",
        f"DISCUSSION_GROUP_ID: {channel_cfg.discussion_group_id}",
        f"REMINDER_CHAT_ID: {channel_cfg.reminder_chat_id}",
    ]

    try:
        ch = await bot.get_chat(channel_cfg.channel_id)
        lines.append(f"Channel title: {ch.title} (type={ch.type})")
        lines.append(f"  linked_chat_id: {ch.linked_chat_id}")
    except Exception as e:
        lines.append(f"Channel error: {e}")

    try:
        gr = await bot.get_chat(channel_cfg.discussion_group_id)
        lines.append(f"Group title: {gr.title} (type={gr.type})")
        lines.append(f"  linked_chat_id: {gr.linked_chat_id}")
    except Exception as e:
        lines.append(f"Group error: {e}")

    try:
        me = await bot.get_me()
        ch_member = await bot.get_chat_member(channel_cfg.channel_id, me.id)
        lines.append(f"Bot in channel: {ch_member.status}")
    except Exception as e:
        lines.append(f"Bot channel membership error: {e}")

    try:
        me = await bot.get_me()
        gr_member = await bot.get_chat_member(channel_cfg.discussion_group_id, me.id)
        lines.append(f"Bot in group: {gr_member.status}")
    except Exception as e:
        lines.append(f"Bot group membership error: {e}")

    await message.reply("\n".join(lines))
