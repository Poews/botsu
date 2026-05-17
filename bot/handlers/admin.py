import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from db import get_settings, add_warning, get_warnings, remove_warning, clear_warnings
from handlers.stats import increment_stat
from utils.helpers import is_admin, get_target_from_message, parse_duration

logger = logging.getLogger(__name__)

HELP_TEXT = """🛡️ <b>Bot de Moderación — Comandos</b>

<b>Acciones sobre usuarios</b> <i>(responde un mensaje o proporciona el ID):</i>
/ban [id] [razón] — Banear permanentemente a un usuario
/unban [id] — Desbanear a un usuario
/kick [id] [razón] — Expulsar a un usuario (puede volver a unirse)
/mute [id] [duración] — Silenciar usuario (ej: 30m, 2h, 1d)
/unmute [id] — Quitar el silencio a un usuario
/warn [id] [razón] — Advertir a un usuario (ban automático al alcanzar el límite)
/unwarn [id] — Eliminar la última advertencia de un usuario
/warnings [id] — Ver todas las advertencias de un usuario

<b>Configuración del grupo:</b>
/settings — Ver la configuración actual del grupo
/set antispam on|off — Activar/desactivar detección de spam
/set antiflood on|off — Activar/desactivar detección de flood
/set maxlength [n|0] — Longitud máxima de mensajes (0 = desactivado)
/set floodlimit [n] — Mensajes permitidos por ventana de tiempo
/set floodwindow [s] — Ventana de detección de flood en segundos
/set warnlimit [n] — Advertencias antes del ban automático
/set deletelinks on|off — Eliminar enlaces de no administradores
/set antiforward on|off — Eliminar mensajes reenviados
/help — Mostrar este mensaje"""


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
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return

    args = context.args or []
    if update.message.reply_to_message:
        reason = " ".join(args) if args else "Sin razón especificada"
    else:
        reason = " ".join(args[1:]) if len(args) > 1 else "Sin razón especificada"

    try:
        await context.bot.ban_chat_member(chat.id, user_id)
        await update.message.reply_text(
            f"🔨 Usuario expulsado correctamente.\n"
            f"👤 Usuario: {mention}\n"
            f"📝 Razón: {reason}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo banear al usuario: {e}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return
    try:
        await context.bot.unban_chat_member(chat.id, user_id, only_if_banned=True)
        await update.message.reply_text(
            f"✅ El usuario {mention} ha sido <b>desbaneado</b> correctamente.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo desbanear al usuario: {e}")


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return

    args = context.args or []
    if update.message.reply_to_message:
        reason = " ".join(args) if args else "Sin razón especificada"
    else:
        reason = " ".join(args[1:]) if len(args) > 1 else "Sin razón especificada"

    try:
        await context.bot.ban_chat_member(chat.id, user_id)
        await context.bot.unban_chat_member(chat.id, user_id)
        await update.message.reply_text(
            f"🔨 Usuario expulsado correctamente.\n"
            f"👤 Usuario: {mention}\n"
            f"📝 Razón: {reason}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo expulsar al usuario: {e}")


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return

    args = context.args or []
    dur_idx = 0 if update.message.reply_to_message else 1
    duration_str = args[dur_idx] if len(args) > dur_idx else None
    duration = parse_duration(duration_str) if duration_str else 0

    until_date = None
    duration_text = "indefinidamente"
    if duration:
        until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
        duration_text = f"por {duration_str}"

    try:
        await context.bot.restrict_chat_member(
            chat.id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        await update.message.reply_text(
            f"🔇 Usuario silenciado correctamente.\n"
            f"👤 Usuario: {mention}\n"
            f"⏱️ Duración: {duration_text}",
            parse_mode="HTML",
        )
        await increment_stat(chat.id, user_id, str(user_id), "mutes")
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo silenciar al usuario: {e}")


async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
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
            f"🔊 El silencio de {mention} ha sido levantado correctamente.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo quitar el silencio al usuario: {e}")


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return

    args = context.args or []
    if update.message.reply_to_message:
        reason = " ".join(args) if args else "Sin razón especificada"
    else:
        reason = " ".join(args[1:]) if len(args) > 1 else "Sin razón especificada"

    settings = await get_settings(chat.id)
    warn_limit = settings["warn_limit"]
    warn_count = await add_warning(chat.id, user_id, reason)

    if warn_count >= warn_limit:
        try:
            await context.bot.ban_chat_member(chat.id, user_id)
            await clear_warnings(chat.id, user_id)
            await update.message.reply_text(
                f"⚠️ Advertencia agregada.\n"
                f"👤 Usuario: {mention}\n"
                f"📝 Razón: {reason}\n"
                f"🔢 Advertencias: {warn_count}/{warn_limit}\n\n"
                f"🔨 Límite alcanzado — el usuario ha sido <b>baneado automáticamente</b>.",
                parse_mode="HTML",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ No se pudo aplicar el ban automático: {e}")
    else:
        await update.message.reply_text(
            f"⚠️ Advertencia agregada.\n"
            f"👤 Usuario: {mention}\n"
            f"📝 Razón: {reason}\n"
            f"🔢 Advertencias: {warn_count}/{warn_limit}",
            parse_mode="HTML",
        )


async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return

    removed = await remove_warning(chat.id, user_id)
    if removed:
        remaining = await get_warnings(chat.id, user_id)
        settings = await get_settings(chat.id)
        await update.message.reply_text(
            f"✅ Última advertencia eliminada.\n"
            f"👤 Usuario: {mention}\n"
            f"🔢 Advertencias restantes: {len(remaining)}/{settings['warn_limit']}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"ℹ️ {mention} no tiene advertencias registradas.",
            parse_mode="HTML",
        )


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)
    if not user_id:
        await update.message.reply_text("❌ Responde a un mensaje o proporciona un ID de usuario.")
        return

    warnings = await get_warnings(chat.id, user_id)
    settings = await get_settings(chat.id)

    if not warnings:
        await update.message.reply_text(
            f"✅ {mention} no tiene advertencias registradas.",
            parse_mode="HTML",
        )
        return

    lines = [f"⚠️ <b>Advertencias de {mention}</b> ({len(warnings)}/{settings['warn_limit']}):\n"]
    for i, w in enumerate(warnings, 1):
        lines.append(f"{i}. {w['reason']}  <i>({w['warned_at']})</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
