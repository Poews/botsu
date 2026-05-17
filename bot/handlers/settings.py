import logging
from telegram import Update
from telegram.ext import ContextTypes

from db import get_settings, update_setting
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

VALID_SETTINGS = {
    "antispam":    ("anti_spam",           "on/off"),
    "antiflood":   ("anti_flood",          "on/off"),
    "maxlength":   ("max_message_length",  "número (0 = desactivado)"),
    "floodlimit":  ("flood_limit",         "número de mensajes"),
    "floodwindow": ("flood_window",        "segundos"),
    "warnlimit":   ("warn_limit",          "número de advertencias antes del ban automático"),
    "deletelinks": ("delete_links",        "on/off"),
    "antiforward": ("anti_forward",        "on/off"),
}

ON_VALUES  = {"on", "true", "yes", "1", "enable", "activar", "si", "sí"}
OFF_VALUES = {"off", "false", "no", "0", "disable", "desactivar"}


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    s = await get_settings(chat.id)

    def yn(val):
        return "✅ Activado" if val else "❌ Desactivado"

    def ml(val):
        return f"{val} caracteres" if val else "❌ Desactivado"

    text = (
        f"⚙️ <b>Configuración — {chat.title}</b>\n\n"
        f"🛡️ Anti-spam:              {yn(s['anti_spam'])}\n"
        f"🌊 Anti-flood:             {yn(s['anti_flood'])}\n"
        f"   ├ Límite:               {s['flood_limit']} mensajes\n"
        f"   └ Ventana:              {s['flood_window']}s\n"
        f"✂️ Longitud máxima:        {ml(s['max_message_length'])}\n"
        f"⚠️ Límite de advertencias: {s['warn_limit']} → ban automático\n"
        f"🔗 Eliminar enlaces:       {yn(s['delete_links'])}\n"
        f"📤 Anti-reenvío:           {yn(s['anti_forward'])}\n\n"
        f"Usa /set [opción] [valor] para cambiar la configuración.\n"
        f"Usa /help para ver todos los comandos."
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
            f"❌ Uso: /set [opción] [valor]\n\nOpciones disponibles: <code>{keys}</code>",
            parse_mode="HTML",
        )
        return

    option = args[0].lower()
    value_str = args[1].lower()

    if option not in VALID_SETTINGS:
        keys = ", ".join(VALID_SETTINGS)
        await update.message.reply_text(
            f"❌ Opción desconocida.\nDisponibles: <code>{keys}</code>",
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
            await update.message.reply_text(
                "❌ El valor debe ser <b>on</b> (activar) o <b>off</b> (desactivar).",
                parse_mode="HTML",
            )
            return
    else:
        try:
            value = int(value_str)
            if value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ El valor debe ser un número positivo.")
            return

    await update_setting(chat.id, db_key, value)
    await update.message.reply_text(
        f"⚙️ Configuración actualizada correctamente.\n<b>{option}</b> → <b>{args[1]}</b>",
        parse_mode="HTML",
    )
