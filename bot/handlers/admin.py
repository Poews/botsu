import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from db import get_settings, add_warning, get_warnings, remove_warning, clear_warnings, get_all_user_ids
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


async def kickdeleted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /kickdeleted — expulsa todas las cuentas eliminadas del grupo.
    Solo admins.
    """
    if not await is_admin(update, context):
        return

    chat = update.effective_chat

    user_ids = await get_all_user_ids(chat.id)
    if not user_ids:
        await update.message.reply_text(
            "ℹ️ No hay usuarios registrados todavía. "
            "El bot solo puede revisar usuarios que hayan enviado al menos un mensaje."
        )
        return

    status_msg = await update.message.reply_text(
        f"🔍 Revisando <b>{len(user_ids)}</b> usuarios registrados, un momento…",
        parse_mode="HTML",
    )

    kicked   = []
    checked  = 0
    BATCH    = 20  # update progress every N users

    for user_id in user_ids:
        try:
            member = await context.bot.get_chat_member(chat.id, user_id)
            # Deleted accounts: still in group but first_name is empty
            if member.status in ("member", "restricted") and not member.user.first_name:
                try:
                    await context.bot.ban_chat_member(chat.id, user_id)
                    await context.bot.unban_chat_member(chat.id, user_id)
                    kicked.append(user_id)
                except Exception:
                    pass
        except Exception:
            pass  # user left, already banned, or API error

        checked += 1
        if checked % BATCH == 0:
            try:
                await status_msg.edit_text(
                    f"🔍 Revisando… <b>{checked}/{len(user_ids)}</b> usuarios\n"
                    f"🗑️ Eliminadas encontradas hasta ahora: <b>{len(kicked)}</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        await asyncio.sleep(0.05)  # avoid hitting rate limits

    if kicked:
        result = (
            f"✅ <b>Limpieza completada.</b>\n\n"
            f"👥 Usuarios revisados: <b>{checked}</b>\n"
            f"🗑️ Cuentas eliminadas expulsadas: <b>{len(kicked)}</b>\n\n"
            f"<i>Nota: solo se revisaron usuarios con historial de mensajes en el grupo.</i>"
        )
    else:
        result = (
            f"✅ <b>Limpieza completada.</b>\n\n"
            f"👥 Usuarios revisados: <b>{checked}</b>\n"
            f"🗑️ Cuentas eliminadas encontradas: <b>0</b>\n\n"
            f"<i>¡El grupo está limpio!</i>"
        )

    await status_msg.edit_text(result, parse_mode="HTML")


async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /say <mensaje>          — (en grupo) borra tu comando y envía el texto como el bot.
    /say <chat_id> <mensaje>— (en privado) envía el texto a ese grupo.
    """
    message = update.message
    user    = update.effective_user
    chat    = update.effective_chat

    args_text = message.text.split(None, 1)
    if len(args_text) < 2:
        await message.reply_text("⚠️ Uso: <code>/say mensaje</code>", parse_mode="HTML")
        return

    payload = args_text[1]

    # ── Desde un grupo ────────────────────────────────────────────────────────
    if chat.type in ("group", "supergroup"):
        if not await is_admin(update, context):
            return
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await context.bot.send_message(chat.id, payload, parse_mode="HTML")
        except Exception:
            # Retry without HTML in case of parse error
            try:
                await context.bot.send_message(chat.id, payload)
            except Exception as e:
                logger.warning("Error en /say: %s", e)
        return

    # ── Desde privado: /say <chat_id> <mensaje> ───────────────────────────────
    parts = payload.split(None, 1)
    if len(parts) < 2 or not parts[0].lstrip("-").isdigit():
        await message.reply_text(
            "⚠️ Desde privado usa:\n"
            "<code>/say -100xxxxxxxxxx mensaje</code>",
            parse_mode="HTML",
        )
        return

    target_chat_id = int(parts[0])
    text           = parts[1]

    # Verify the sender is admin in that group before allowing it
    try:
        member = await context.bot.get_chat_member(target_chat_id, user.id)
        if member.status not in ("administrator", "creator"):
            await message.reply_text("⛔ Solo puedes enviar mensajes a grupos donde eres administrador.")
            return
    except Exception:
        await message.reply_text("⚠️ No pude verificar tus permisos en ese grupo. ¿El bot está ahí?")
        return

    try:
        await context.bot.send_message(target_chat_id, text, parse_mode="HTML")
        await message.reply_text("✅ Mensaje enviado.")
    except Exception:
        try:
            await context.bot.send_message(target_chat_id, text)
            await message.reply_text("✅ Mensaje enviado (sin formato HTML).")
        except Exception as e:
            await message.reply_text(f"❌ Error al enviar: {e}")


async def cmds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cmds — lista completa de comandos del bot."""
    text = (
        "📋 <b>Comandos disponibles</b>\n"
        "\n"
        "👮 <b>Moderación</b>\n"
        "  /ban — Banear usuario\n"
        "  /unban — Desbanear usuario\n"
        "  /kick — Expulsar usuario\n"
        "  /mute — Silenciar usuario\n"
        "  /unmute — Quitar silencio\n"
        "  /warn — Advertir usuario\n"
        "  /unwarn — Quitar advertencia\n"
        "  /warnings — Ver advertencias de un usuario\n"
        "  /kickdeleted — Expulsar cuentas eliminadas\n"
        "\n"
        "⚙️ <b>Configuración</b>\n"
        "  /settings — Ver configuración actual del grupo\n"
        "  /set — Cambiar una configuración\n"
        "  /reload — Limpiar caché y verificar estado\n"
        "  /say — Enviar mensaje como el bot\n"
        "\n"
        "📝 <b>Notas</b>\n"
        "  /nota — Guardar nota sobre un usuario\n"
        "  /notas — Ver notas de un usuario\n"
        "  /borrarnota — Eliminar una nota\n"
        "\n"
        "🚫 <b>Lista negra</b>\n"
        "  /addpalabra — Añadir palabra prohibida\n"
        "  /quitarpalabra — Quitar palabra prohibida\n"
        "  /palabras — Ver palabras prohibidas\n"
        "  /limpiarpalabras — Borrar toda la lista negra\n"
        "\n"
        "🤖 <b>Comandos personales</b>\n"
        "  /personal — Crear comando personalizado\n"
        "  /personales — Ver comandos creados\n"
        "  /borrarpersonal — Eliminar comando personalizado\n"
        "\n"
        "📊 <b>Estadísticas y reportes</b>\n"
        "  /estadisticas — Ver estadísticas del grupo\n"
        "  /report — Reportar un mensaje (responder al mensaje)\n"
        "  /reportes — Ver reportes pendientes (admins)\n"
        "\n"
        "ℹ️ <b>General</b>\n"
        "  /start — Iniciar el bot\n"
        "  /help — Mostrar ayuda\n"
        "  /cmds — Esta lista\n"
        "  /staff — Ver equipo de administración\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reload — limpia cachés en memoria y confirma que el bot está activo.
    Solo admins.
    """
    if not await is_admin(update, context):
        return

    from handlers.moderation import flood_tracker, spam_tracker

    flood_count = len(flood_tracker)
    spam_count  = len(spam_tracker)

    flood_tracker.clear()
    spam_tracker.clear()

    chat = update.effective_chat
    settings = await get_settings(chat.id)

    def yn(v): return "✅" if v else "❌"

    await update.message.reply_text(
        f"🔄 <b>Bot recargado correctamente.</b>\n\n"
        f"🗑️ Caché limpiado:\n"
        f"   ├ Flood tracker: <b>{flood_count}</b> entradas eliminadas\n"
        f"   └ Spam tracker:  <b>{spam_count}</b> entradas eliminadas\n\n"
        f"⚙️ Configuración activa:\n"
        f"   ├ Anti-spam:   {yn(settings['anti_spam'])}\n"
        f"   ├ Anti-flood:  {yn(settings['anti_flood'])}\n"
        f"   ├ Blacklist:   ✅\n"
        f"   └ Bienvenida:  {'✅' if settings.get('welcome_message') else '🟢 (por defecto)'}\n\n"
        f"🤖 El bot está activo y escuchando.",
        parse_mode="HTML",
    )
