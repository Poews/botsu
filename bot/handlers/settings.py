import logging
from telegram import Update
from telegram.ext import ContextTypes

from db import get_settings, update_setting
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

TOGGLE_SETTINGS = {
    "antispam":    "anti_spam",
    "antiflood":   "anti_flood",
    "deletelinks": "delete_links",
    "antiforward": "anti_forward",
}

NUMBER_SETTINGS = {
    "maxlength":   "max_message_length",
    "floodlimit":  "flood_limit",
    "floodwindow": "flood_window",
    "warnlimit":   "warn_limit",
}

ON_VALUES  = {"on", "true", "yes", "1", "enable", "activar", "si", "sí"}
OFF_VALUES = {"off", "false", "no", "0", "disable", "desactivar"}

ALL_OPTIONS = (
    list(TOGGLE_SETTINGS) + list(NUMBER_SETTINGS) + ["welcome"]
)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    s = await get_settings(chat.id)

    def yn(val):
        return "✅ Activado" if val else "❌ Desactivado"

    def ml(val):
        return f"{val} caracteres" if val else "❌ Desactivado"

    welcome_raw = s.get("welcome_message")
    welcome_display = f"<code>{welcome_raw}</code>" if welcome_raw else "❌ Desactivado"

    text = (
        f"⚙️ <b>Configuración — {chat.title}</b>\n\n"
        f"🛡️ Anti-spam:              {yn(s['anti_spam'])}\n"
        f"🌊 Anti-flood:             {yn(s['anti_flood'])}\n"
        f"   ├ Límite:               {s['flood_limit']} mensajes\n"
        f"   └ Ventana:              {s['flood_window']}s\n"
        f"✂️ Longitud máxima:        {ml(s['max_message_length'])}\n"
        f"⚠️ Límite de advertencias: {s['warn_limit']} → ban automático\n"
        f"🔗 Eliminar enlaces:       {yn(s['delete_links'])}\n"
        f"📤 Anti-reenvío:           {yn(s['anti_forward'])}\n"
        f"👋 Bienvenida:             {welcome_display}\n\n"
        f"<i>Variables disponibles en la bienvenida: "
        f"{{usuario}}, {{nombre}}, {{grupo}}</i>\n\n"
        f"Usa /set [opción] [valor] para cambiar la configuración.\n"
        f"Usa /help para ver todos los comandos."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    message_text = update.effective_message.text or ""
    args = context.args

    if not args:
        opts = ", ".join(ALL_OPTIONS)
        await update.message.reply_text(
            f"❌ Uso: /set [opción] [valor]\n\nOpciones disponibles: <code>{opts}</code>",
            parse_mode="HTML",
        )
        return

    option = args[0].lower()

    if option not in ALL_OPTIONS:
        opts = ", ".join(ALL_OPTIONS)
        await update.message.reply_text(
            f"❌ Opción desconocida.\nDisponibles: <code>{opts}</code>",
            parse_mode="HTML",
        )
        return

    if len(args) < 2:
        await update.message.reply_text(
            f"❌ Uso: /set {option} [valor]"
        )
        return

    # ── welcome: takes the rest of the message as free text ──────────────────
    if option == "welcome":
        # Extract everything after "/set welcome "
        prefix = message_text.split(None, 2)
        if len(prefix) < 3:
            await update.message.reply_text(
                "❌ Uso: /set welcome [mensaje]\n\n"
                "Escribe <b>off</b> para desactivar.\n"
                "Variables: <code>{usuario}</code>, <code>{nombre}</code>, <code>{grupo}</code>",
                parse_mode="HTML",
            )
            return

        value_text = prefix[2].strip()

        if value_text.lower() in OFF_VALUES:
            await update_setting(chat.id, "welcome_message", None)
            await update.message.reply_text(
                "⚙️ Configuración actualizada correctamente.\n"
                "👋 Mensaje de bienvenida <b>desactivado</b>.",
                parse_mode="HTML",
            )
        else:
            await update_setting(chat.id, "welcome_message", value_text)
            preview = value_text.replace("{usuario}", "<b>NombreUsuario</b>") \
                                 .replace("{nombre}", "Nombre") \
                                 .replace("{grupo}", chat.title or "Grupo")
            await update.message.reply_text(
                f"⚙️ Configuración actualizada correctamente.\n"
                f"👋 Mensaje de bienvenida guardado.\n\n"
                f"<b>Vista previa:</b>\n{preview}",
                parse_mode="HTML",
            )
        return

    # ── toggle settings ───────────────────────────────────────────────────────
    if option in TOGGLE_SETTINGS:
        value_str = args[1].lower()
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
        db_key = TOGGLE_SETTINGS[option]
        await update_setting(chat.id, db_key, value)
        await update.message.reply_text(
            f"⚙️ Configuración actualizada correctamente.\n"
            f"<b>{option}</b> → <b>{args[1]}</b>",
            parse_mode="HTML",
        )
        return

    # ── number settings ───────────────────────────────────────────────────────
    if option in NUMBER_SETTINGS:
        try:
            value = int(args[1])
            if value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ El valor debe ser un número positivo.")
            return
        db_key = NUMBER_SETTINGS[option]
        await update_setting(chat.id, db_key, value)
        await update.message.reply_text(
            f"⚙️ Configuración actualizada correctamente.\n"
            f"<b>{option}</b> → <b>{args[1]}</b>",
            parse_mode="HTML",
        )
