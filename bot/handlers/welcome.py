import logging
from telegram import Update, ChatMemberUpdated, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes

from db import get_settings

logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "🟢 (+) <b>{usuario}</b> es el usuario <code>{id}</code>"

NO_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)


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

    if has_username:
        try:
            await context.bot.send_message(chat.id, text, parse_mode="HTML")
        except Exception as e:
            logger.warning("Error al enviar bienvenida: %s", e)
        return

    # ── No username: mute + group notice + register pending ──────────────────
    from handlers.verify import pending_users, NO_PERMISSIONS as _NP

    try:
        await context.bot.restrict_chat_member(chat.id, user.id, _NP)
    except Exception as e:
        logger.warning("Error al mutear usuario sin @: %s", e)

    pending_users.setdefault(user.id, set()).add(chat.id)

    bot_username = (await context.bot.get_me()).username
    start_param  = f"verify_{chat.id}"
    bot_url      = f"https://t.me/{bot_username}?start={start_param}"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🤖 Verificar @usuario", url=bot_url)
    ]])

    try:
        await context.bot.send_message(
            chat.id,
            f"⚠️ {user.mention_html()} no tiene <b>@usuario</b> y ha sido muteado temporalmente.\n\n"
            f"Presiona el botón para iniciar el bot en privado, ponerte un @usuario y ser habilitado automáticamente.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning("Error al enviar aviso sin @usuario: %s", e)
