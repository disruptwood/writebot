"""Admin-only commands for managing the writing channel."""

import logging

from aiogram import Router, types, F, Bot
from aiogram.filters import Command

from bot.config import DISCUSSION_GROUP_ID, CHANNEL_ID, STRINGS, INITIAL_ADMIN_ID
from bot.db import queries

logger = logging.getLogger(__name__)
router = Router()

# Only in discussion group
router.message.filter(F.chat.id == DISCUSSION_GROUP_ID)


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
        await message.answer(STRINGS["not_admin"])
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Ответьте на сообщение пользователя, которого хотите сделать админом.")
        return

    target = message.reply_to_message.from_user
    await queries.add_admin(target.id, target.username, target.first_name, message.from_user.id)
    name = f"@{target.username}" if target.username else target.first_name
    await message.answer(STRINGS["admin_added"].format(name=name))


@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: types.Message):
    """Remove a bot admin. Usage: /removeadmin (reply to user's message)."""
    if not await _check_admin(message):
        await message.answer(STRINGS["not_admin"])
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Ответьте на сообщение пользователя, которого хотите убрать из админов.")
        return

    target = message.reply_to_message.from_user
    removed = await queries.remove_admin(target.id)
    name = f"@{target.username}" if target.username else target.first_name

    if removed:
        await message.answer(STRINGS["admin_removed"].format(name=name))
    else:
        await message.answer(f"{name} не является админом.")


@router.message(Command("kick_inactive"))
async def cmd_kick_inactive(message: types.Message, bot: Bot):
    """List or kick inactive members. Usage: /kick_inactive [days] [confirm]."""
    if not await _check_admin(message):
        await message.answer(STRINGS["not_admin"])
        return

    args = (message.text or "").split()
    days = 7  # default
    confirm = False

    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass
    if len(args) > 2 and args[2].lower() == "confirm":
        confirm = True

    inactive = await queries.get_inactive_members(days)
    if not inactive:
        await message.answer(f"Все участники писали в последние {days} дней!")
        return

    if not confirm:
        names = ", ".join(
            f"@{m['username']}" if m.get("username") else (m.get("first_name") or str(m["user_id"]))
            for m in inactive
        )
        await message.answer(
            f"{STRINGS['kick_list'].format(days=days, names=names)}\n\n"
            f"Для удаления: /kick_inactive {days} confirm"
        )
        return

    # Actually kick from both channel and discussion group
    kicked = []
    for m in inactive:
        uid = m["user_id"]
        name = f"@{m['username']}" if m.get("username") else (m.get("first_name") or str(uid))
        try:
            # Kick from channel
            await bot.ban_chat_member(CHANNEL_ID, uid)
            await bot.unban_chat_member(CHANNEL_ID, uid)
            # Kick from discussion group
            try:
                await bot.ban_chat_member(DISCUSSION_GROUP_ID, uid)
                await bot.unban_chat_member(DISCUSSION_GROUP_ID, uid)
            except Exception as e:
                logger.warning("Could not kick %s from discussion group: %s", uid, e)
            await queries.deactivate_member(uid)
            kicked.append(name)
            logger.info("Kicked inactive user %s from channel+group", uid)
        except Exception as e:
            logger.error("Failed to kick user %s: %s", uid, e)

    if kicked:
        await message.answer(f"Удалены: {', '.join(kicked)}")
    else:
        await message.answer("Не удалось удалить ни одного участника.")


@router.message(Command("reinvite"))
async def cmd_reinvite(message: types.Message, bot: Bot):
    """Create an invite link for a kicked member. Usage: /reinvite (reply) or /reinvite user_id."""
    if not await _check_admin(message):
        await message.answer(STRINGS["not_admin"])
        return

    # Determine target user
    target_id = None
    target_name = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_name = (
            f"@{message.reply_to_message.from_user.username}"
            if message.reply_to_message.from_user.username
            else message.reply_to_message.from_user.first_name
        )
    else:
        # Try to parse user_id from command args
        args = (message.text or "").split()
        if len(args) > 1:
            try:
                target_id = int(args[1])
            except ValueError:
                pass

    if not target_id:
        await message.answer(
            "Ответьте на сообщение пользователя или укажите user_id:\n"
            "/reinvite 123456789"
        )
        return

    # Look up member info if we don't have a name
    if not target_name:
        member = await queries.get_member(target_id)
        if member:
            target_name = (
                f"@{member['username']}" if member.get("username")
                else (member.get("first_name") or str(target_id))
            )
        else:
            target_name = str(target_id)

    # Make sure they're unbanned in both channel and group
    for chat_id, chat_name in [(CHANNEL_ID, "канал"), (DISCUSSION_GROUP_ID, "чат")]:
        try:
            await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
        except Exception as e:
            logger.warning("Could not unban %s in %s: %s", target_id, chat_name, e)

    # Reactivate in DB
    await queries.reactivate_member(target_id)

    # Create a one-time invite link for the channel
    try:
        invite = await bot.create_chat_invite_link(
            CHANNEL_ID,
            member_limit=1,
            name=f"reinvite-{target_id}",
        )
        await message.answer(
            f"{STRINGS['reinvited'].format(name=target_name)}\n"
            f"Ссылка для входа (одноразовая): {invite.invite_link}"
        )
    except Exception as e:
        logger.error("Failed to create invite link: %s", e)
        await message.answer(
            f"{target_name} разбанен, но не удалось создать ссылку: {e}\n"
            "Можно добавить вручную."
        )


@router.message(Command("debug_channel"))
async def cmd_debug_channel(message: types.Message, bot: Bot):
    """Show diagnostic info about channel/group setup. Admin only."""
    if not await _check_admin(message):
        await message.answer(STRINGS["not_admin"])
        return

    lines = [
        f"CHANNEL_ID: {CHANNEL_ID}",
        f"DISCUSSION_GROUP_ID: {DISCUSSION_GROUP_ID}",
    ]

    # Check channel info
    try:
        ch = await bot.get_chat(CHANNEL_ID)
        lines.append(f"Channel: {ch.title} (type={ch.type})")
        lines.append(f"  linked_chat_id: {ch.linked_chat_id}")
    except Exception as e:
        lines.append(f"Channel error: {e}")

    # Check group info
    try:
        gr = await bot.get_chat(DISCUSSION_GROUP_ID)
        lines.append(f"Group: {gr.title} (type={gr.type})")
        lines.append(f"  linked_chat_id: {gr.linked_chat_id}")
    except Exception as e:
        lines.append(f"Group error: {e}")

    # Check bot's own membership
    try:
        me = await bot.get_me()
        ch_member = await bot.get_chat_member(CHANNEL_ID, me.id)
        lines.append(f"Bot in channel: {ch_member.status}")
    except Exception as e:
        lines.append(f"Bot channel membership error: {e}")

    try:
        me = await bot.get_me()
        gr_member = await bot.get_chat_member(DISCUSSION_GROUP_ID, me.id)
        lines.append(f"Bot in group: {gr_member.status}")
    except Exception as e:
        lines.append(f"Bot group membership error: {e}")

    # Recent unattributed posts
    from bot.db import queries as q
    state = await q.get_state("unattributed_posts_count")
    if state:
        lines.append(f"Unattributed posts (no from_user): {state}")

    await message.answer("\n".join(lines))
