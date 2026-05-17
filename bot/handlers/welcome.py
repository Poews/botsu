import logging
from telegram import Update, ChatMemberUpdated, ChatMember
from telegram.ext import ContextTypes

from db import get_settings

logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "✅ ¡Bienvenido al grupo, {usuario}! 👋"


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

    settings = await get_settings(chat.id)
    template = settings.get("welcome_message") or DEFAULT_WELCOME

    text = template.replace("{usuario}", user.mention_html())
    text = text.replace("{nombre}",  user.first_name)
    text = text.replace("{grupo}",   chat.title or "")

    try:
        await context.bot.send_message(chat.id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Error al enviar bienvenida: %s", e)
