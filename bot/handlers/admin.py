import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from db import get_settings, add_warning, get_warnings, remove_warning, clear_warnings
from utils.helpers import is_admin, get_target_from_message, parse_duration

logger = logging.getLogger(__name__)

HELP_TEXT = """🛡️ <b>Moderation Bot — Commands</b>

<b>User Actions (reply to a message or pass user ID):</b>
/ban [id] [reason] — Permanently ban a user
/unban [id] — Unban a user
/kick [id] [reason] — Kick a user (they can rejoin)
/mute [id] [duration] — Restrict a user (e.g. 30m, 2h, 1d)
/unmute [id] — Restore a user's ability to speak
/warn [id] [reason] — Warn a user (auto-bans at the limit)
/unwarn [id] — Remove the user's most recent warning
/warnings [id] — List all warnings for a user

<b>Configuration:</b>
/settings — Show current group settings
/set antispam on|off — Toggle duplicate-message detection
/set antiflood on|off — Toggle flood detection
/set maxlength [n|0] — Max message length (0 = disabled)
/set floodlimit [n] — Messages allowed per flood window
/set floodwindow [s] — Flood detection window in seconds
/set warnlimit [n] — Warnings before auto-ban
/set deletelinks on|off — Auto-delete links from non-admins
/set antiforward on|off — Auto-delete forwarded messages
/help — Show this message"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return

    args = context.args or []
    if update.message.reply_to_message:
        reason = " ".join(args) if args else "No reason provided"
    else:
        reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided"

    try:
        await context.bot.ban_chat_member(chat.id, user_id)
        await update.message.reply_text(
            f"🔨 {mention} has been <b>banned</b>.\n📝 Reason: {reason}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to ban: {e}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return
    try:
        await context.bot.unban_chat_member(chat.id, user_id, only_if_banned=True)
        await update.message.reply_text(
            f"✅ {mention} has been <b>unbanned</b>.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unban: {e}")


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return

    args = context.args or []
    if update.message.reply_to_message:
        reason = " ".join(args) if args else "No reason provided"
    else:
        reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided"

    try:
        await context.bot.ban_chat_member(chat.id, user_id)
        await context.bot.unban_chat_member(chat.id, user_id)
        await update.message.reply_text(
            f"👢 {mention} has been <b>kicked</b>.\n📝 Reason: {reason}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to kick: {e}")


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return

    args = context.args or []
    dur_idx = 0 if update.message.reply_to_message else 1
    duration_str = args[dur_idx] if len(args) > dur_idx else None
    duration = parse_duration(duration_str) if duration_str else 0

    until_date = None
    duration_text = "indefinitely"
    if duration:
        until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
        duration_text = f"for {duration_str}"

    try:
        await context.bot.restrict_chat_member(
            chat.id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        await update.message.reply_text(
            f"🔇 {mention} has been <b>muted</b> {duration_text}.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to mute: {e}")


async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return
    try:
        await context.bot.restrict_chat_member(
            chat.id,
            user_id,
            ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
        )
        await update.message.reply_text(
            f"🔊 {mention} has been <b>unmuted</b>.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unmute: {e}")


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return

    args = context.args or []
    if update.message.reply_to_message:
        reason = " ".join(args) if args else "No reason provided"
    else:
        reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided"

    settings = await get_settings(chat.id)
    warn_limit = settings["warn_limit"]
    warn_count = await add_warning(chat.id, user_id, reason)

    if warn_count >= warn_limit:
        try:
            await context.bot.ban_chat_member(chat.id, user_id)
            await clear_warnings(chat.id, user_id)
            await update.message.reply_text(
                f"⚠️ {mention} warned ({warn_count}/{warn_limit}): {reason}\n"
                f"🔨 Warning limit reached — user has been <b>auto-banned</b>.",
                parse_mode="HTML",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Auto-ban failed: {e}")
    else:
        await update.message.reply_text(
            f"⚠️ {mention} has been <b>warned</b> ({warn_count}/{warn_limit}).\n"
            f"📝 Reason: {reason}",
            parse_mode="HTML",
        )


async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return

    removed = await remove_warning(chat.id, user_id)
    if removed:
        remaining = await get_warnings(chat.id, user_id)
        settings = await get_settings(chat.id)
        await update.message.reply_text(
            f"✅ Last warning removed from {mention}. "
            f"Now at {len(remaining)}/{settings['warn_limit']}.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"ℹ️ {mention} has no warnings to remove.",
            parse_mode="HTML",
        )


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Reply to a message or provide a user ID.")
        return

    warnings = await get_warnings(chat.id, user_id)
    settings = await get_settings(chat.id)

    if not warnings:
        await update.message.reply_text(
            f"✅ {mention} has no warnings.",
            parse_mode="HTML",
        )
        return

    lines = [f"⚠️ <b>Warnings for {mention}</b> ({len(warnings)}/{settings['warn_limit']}):\n"]
    for i, w in enumerate(warnings, 1):
        lines.append(f"{i}. {w['reason']}  <i>({w['warned_at']})</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
