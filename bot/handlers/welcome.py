import logging
from telegram import Update, ChatMemberUpdated, ChatMember
from telegram.ext import ContextTypes

from db import get_settings

logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "🟢 (+) <b>{usuario}</b> es el usuario <code>{id}</code>"


def _member_joined(update: ChatMemberUpdated) -> bool:
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    was_out = old_status in (ChatMember.LEFT, ChatMember.BANNED)
    is_in   = new_status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    return was_out and is_in


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member_update = update.chat_member
    if not chat_member_update:
        return
    if not _member_joined(chat_member_update):
        return

    chat = chat_member_update.chat
    user = chat_member_update.new_chat_member.user

    if user.is_bot:
        return

    full_name = " ".join(p for p in [user.first_name or "", user.last_name or ""] if p).strip()
    has_username = bool(user.username)
    display = f"@{user.username}" if has_username else full_name

    settings = await get_settings(chat.id)
    template = settings.get("welcome_message") or DEFAULT_WELCOME

    text = template.replace("{usuario}", display)
    text = text.replace("{nombre}",  full_name)
    text = text.replace("{grupo}",   chat.title or "")
    text = text.replace("{id}",      str(user.id))

    try:
        await context.bot.send_message(chat.id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Error al enviar bienvenida: %s", e)

    if not has_username:
        try:
            await context.bot.send_message(
                user.id,
                f"👋 ¡Bienvenido/a al grupo <b>{chat.title}</b>!\n\n"
                f"📌 Notamos que <b>no tienes un @usuario</b> configurado en tu cuenta de Telegram.\n\n"
                f"Te pedimos que establezcas uno para poder identificarte correctamente en el grupo. "
                f"Puedes hacerlo desde:\n"
                f"<b>Ajustes → Editar perfil → Nombre de usuario</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
