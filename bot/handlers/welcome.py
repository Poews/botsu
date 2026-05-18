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

VERIFY_TIMEOUT = 60  # seconds before kicking unverified user


def _member_joined(update: ChatMemberUpdated) -> bool:
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    was_out = old_status in (ChatMember.LEFT, ChatMember.BANNED)
    is_in   = new_status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    return was_out and is_in


async def _kick_unverified(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job: if the user still hasn't verified after VERIFY_TIMEOUT, kick + delete message."""
    from handlers.verify import pending_users

    data      = context.job.data
    chat_id   = data["chat_id"]
    user_id   = data["user_id"]
    msg_id    = data["msg_id"]
    user_name = data["user_name"]

    # If user already verified, do nothing
    if user_id not in pending_users or chat_id not in pending_users.get(user_id, set()):
        return

    pending_users.get(user_id, set()).discard(chat_id)
    if not pending_users.get(user_id):
        pending_users.pop(user_id, None)

    # Delete the warning message
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except Exception:
        pass

    # Kick (ban then unban = kick without permanent ban)
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)
    except Exception as e:
        logger.warning("Error al kickear usuario sin @: %s", e)

    # Brief notification that auto-disappears isn't possible in Telegram,
    # so we send a short notice and schedule its deletion after 10 seconds.
    try:
        notice = await context.bot.send_message(
            chat_id,
            f"👢 <b>{user_name}</b> fue expulsado por no verificar su @usuario a tiempo.",
            parse_mode="HTML",
        )
        context.job_queue.run_once(
            _delete_msg,
            when=10,
            data={"chat_id": chat_id, "msg_id": notice.message_id},
        )
    except Exception as e:
        logger.warning("Error al notificar kick sin @: %s", e)


async def _delete_msg(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job: delete a message by id."""
    data = context.job.data
    try:
        await context.bot.delete_message(data["chat_id"], data["msg_id"])
    except Exception:
        pass


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

    # ── No username: mute + group notice + register pending + schedule kick ──
    from handlers.verify import pending_users

    try:
        await context.bot.restrict_chat_member(chat.id, user.id, NO_PERMISSIONS)
    except Exception as e:
        logger.warning("Error al mutear usuario sin @: %s", e)

    pending_users.setdefault(user.id, set()).add(chat.id)

    bot_username = (await context.bot.get_me()).username
    bot_url      = f"https://t.me/{bot_username}?start=verify_{chat.id}"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🤖 Verificar @usuario", url=bot_url)
    ]])

    notice_msg = None
    try:
        notice_msg = await context.bot.send_message(
            chat.id,
            f"⚠️ {user.mention_html()} no tiene <b>@usuario</b> y ha sido muteado.\n\n"
            f"Tienes <b>1 minuto</b> para presionar el botón, iniciar el bot en privado "
            f"y ponerte un @usuario. Si no lo haces serás expulsado automáticamente.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning("Error al enviar aviso sin @usuario: %s", e)

    # Schedule the kick job
    if notice_msg and context.job_queue:
        context.job_queue.run_once(
            _kick_unverified,
            when=VERIFY_TIMEOUT,
            data={
                "chat_id":   chat.id,
                "user_id":   user.id,
                "msg_id":    notice_msg.message_id,
                "user_name": full_name,
            },
        )
