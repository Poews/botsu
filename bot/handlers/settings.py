import logging
from telegram import Update
from telegram.ext import ContextTypes

from db import get_settings, update_setting
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

VALID_SETTINGS = {
    "antispam":    ("anti_spam",           "on/off"),
    "antiflood":   ("anti_flood",          "on/off"),
    "maxlength":   ("max_message_length",  "number (0 = disabled)"),
    "floodlimit":  ("flood_limit",         "number of messages"),
    "floodwindow": ("flood_window",        "seconds"),
    "warnlimit":   ("warn_limit",          "number of warnings before auto-ban"),
    "deletelinks": ("delete_links",        "on/off"),
    "antiforward": ("anti_forward",        "on/off"),
}

ON_VALUES  = {"on", "true", "yes", "1", "enable"}
OFF_VALUES = {"off", "false", "no", "0", "disable"}


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    s = await get_settings(chat.id)

    def yn(val):
        return "✅ On" if val else "❌ Off"

    def ml(val):
        return f"{val} chars" if val else "❌ Disabled"

    text = (
        f"⚙️ <b>Settings — {chat.title}</b>\n\n"
        f"🛡️ Anti-spam:          {yn(s['anti_spam'])}\n"
        f"🌊 Anti-flood:         {yn(s['anti_flood'])}\n"
        f"   ├ Limit:            {s['flood_limit']} msgs\n"
        f"   └ Window:           {s['flood_window']}s\n"
        f"✂️ Max msg length:     {ml(s['max_message_length'])}\n"
        f"⚠️ Warn limit:         {s['warn_limit']} warns → auto-ban\n"
        f"🔗 Delete links:       {yn(s['delete_links'])}\n"
        f"📤 Anti-forward:       {yn(s['anti_forward'])}\n\n"
        f"Use /set [option] [value] to change.\n"
        f"Use /help to see all commands."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    args = context.args

    if not args or len(args) < 2:
        keys = ", ".join(VALID_SETTINGS)
        await update.message.reply_text(
            f"❌ Usage: /set [option] [value]\n\nOptions: <code>{keys}</code>",
            parse_mode="HTML",
        )
        return

    option = args[0].lower()
    value_str = args[1].lower()

    if option not in VALID_SETTINGS:
        keys = ", ".join(VALID_SETTINGS)
        await update.message.reply_text(
            f"❌ Unknown option.\nAvailable: <code>{keys}</code>",
            parse_mode="HTML",
        )
        return

    db_key, description = VALID_SETTINGS[option]

    if "on/off" in description:
        if value_str in ON_VALUES:
            value = 1
        elif value_str in OFF_VALUES:
            value = 0
        else:
            await update.message.reply_text("❌ Value must be <b>on</b> or <b>off</b>.", parse_mode="HTML")
            return
    else:
        try:
            value = int(value_str)
            if value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Value must be a non-negative number.")
            return

    await update_setting(chat.id, db_key, value)
    await update.message.reply_text(
        f"✅ <b>{option}</b> → <b>{args[1]}</b>",
        parse_mode="HTML",
    )
