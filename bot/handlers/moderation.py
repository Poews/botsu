import time
import re
import logging
from collections import defaultdict, deque
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from db import get_settings, is_free_user
from handlers.stats import increment_stat
from handlers.blacklist import check_blacklist
from handlers.logchannel import log_event
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

flood_tracker: dict = defaultdict(deque)
spam_tracker: dict = defaultdict(deque)

# Long-message warning tracker: {(chat_id, user_id): {"msg_id": int, "count": int}}
longmsg_tracker: dict = {}

URL_PATTERN = re.compile(
    r"(https?://[^\s]+|www\.[^\s]+|t\.me/[^\s]+)",
    re.IGNORECASE,
)


def _display_name(user) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(p for p in parts if p).strip() or str(user.id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if await is_admin(update, context):
        return

    if await is_free_user(chat.id, user.id):
        await increment_stat(chat.id, user.id, name, "messages")
        return

    settings = await get_settings(chat.id)
    text = message.text or message.caption or ""
    name = _display_name(user)

    # Blacklist check runs first
    if text and await check_blacklist(update, context, text):
        return

    if settings["anti_flood"]:
        if _is_flooding(chat.id, user.id, settings["flood_limit"], settings["flood_window"]):
            try:
                await message.delete()
            except Exception:
                pass
            try:
                until = int(time.time()) + 60
                await context.bot.restrict_chat_member(
                    chat.id,
                    user.id,
                    ChatPermissions(can_send_messages=False),
                    until_date=until,
                )
                await context.bot.send_message(
                    chat.id,
                    f"⏳ {user.mention_html()}, estás enviando mensajes demasiado rápido. "
                    f"Espera unos segundos. Has sido silenciado por 1 minuto.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Error al silenciar por flood: %s", e)
            await increment_stat(chat.id, user.id, name, "floods")
            await increment_stat(chat.id, user.id, name, "mutes")
            await log_event(context.bot, chat.id, chat.title, "FLOOD",
                            user.mention_html(), user.id, reason="Flood detectado", extra="Silenciado 1 minuto")
            return

    if settings["anti_spam"] and text:
        if _is_spam(chat.id, user.id, text):
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await context.bot.send_message(
                    chat.id,
                    f"🚫 {user.mention_html()}, por favor evita enviar spam o mensajes repetitivos.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Error al notificar spam: %s", e)
            await increment_stat(chat.id, user.id, name, "spam")
            await log_event(context.bot, chat.id, chat.title, "SPAM",
                            user.mention_html(), user.id, reason="Mensajes repetitivos")
            return

    if settings["max_message_length"] and len(text) > settings["max_message_length"]:
        try:
            await message.delete()
        except Exception:
            pass
        await _handle_long_message(update, context, settings)
        return

    if settings["anti_forward"] and (
        message.forward_date or message.forward_from or message.forward_from_chat
    ):
        try:
            await message.delete()
        except Exception:
            pass
        return

    if settings["delete_links"] and text and URL_PATTERN.search(text):
        try:
            await message.delete()
            await context.bot.send_message(
                chat.id,
                f"🔗 {user.mention_html()}, los enlaces no están permitidos en este grupo.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Error al eliminar enlace: %s", e)
        return

    # Message passed all checks — count it
    await increment_stat(chat.id, user.id, name, "messages")


async def _handle_long_message(update, context, settings):
    """
    Sends ONE warning message in the group and edits it on repeat offenses.
    On the 3rd offense the user is muted permanently.
    """
    from telegram import ChatPermissions

    user = update.effective_user
    chat = update.effective_chat
    key  = (chat.id, user.id)

    entry = longmsg_tracker.get(key, {"msg_id": None, "count": 0})
    count = entry["count"] + 1
    limit = settings["max_message_length"]

    MUTE_AT = 3
    bars = "🟥" * count + "⬜" * (MUTE_AT - count)

    if count < MUTE_AT:
        text = (
            f"✂️ {user.mention_html()}, tu mensaje superó el límite de <b>{limit}</b> caracteres y fue eliminado.\n"
            f"⚠️ Advertencia <b>{count}/{MUTE_AT}</b>  {bars}\n"
            f"<i>A la 3ª advertencia serás muteado permanentemente.</i>"
        )
    else:
        text = (
            f"✂️ {user.mention_html()}, tu mensaje superó el límite de <b>{limit}</b> caracteres y fue eliminado.\n"
            f"🔇 Advertencia <b>{count}/{MUTE_AT}</b>  {bars} — <b>Muteado permanentemente.</b>"
        )

    # Try to edit the existing warning message, fall back to sending a new one
    sent_id = None
    if entry["msg_id"]:
        try:
            await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=entry["msg_id"],
                text=text,
                parse_mode="HTML",
            )
            sent_id = entry["msg_id"]
        except Exception:
            sent_id = None

    if sent_id is None:
        try:
            sent = await context.bot.send_message(chat.id, text, parse_mode="HTML")
            sent_id = sent.message_id
        except Exception as e:
            logger.warning("Error al enviar aviso de mensaje largo: %s", e)

    if count >= MUTE_AT:
        # Mute permanently (no until_date = indefinite)
        try:
            await context.bot.restrict_chat_member(
                chat.id,
                user.id,
                ChatPermissions(can_send_messages=False),
            )
        except Exception as e:
            logger.warning("Error al silenciar por mensajes largos: %s", e)
        await log_event(context.bot, chat.id, chat.title, "MUTE AUTO",
                        user.mention_html(), user.id,
                        reason=f"Mensajes demasiado largos (límite: {limit} caracteres)",
                        extra="Muteado permanentemente")
        # Reset tracker after mute
        longmsg_tracker.pop(key, None)
    else:
        longmsg_tracker[key] = {"msg_id": sent_id, "count": count}


def _is_flooding(chat_id: int, user_id: int, limit: int, window: int) -> bool:
    key = (chat_id, user_id)
    now = time.time()
    q = flood_tracker[key]
    while q and q[0] < now - window:
        q.popleft()
    q.append(now)
    return len(q) > limit


def _is_spam(chat_id: int, user_id: int, text: str) -> bool:
    key = (chat_id, user_id)
    now = time.time()
    q = spam_tracker[key]
    while q and q[0][0] < now - 60:
        q.popleft()
    normalized = text.strip().lower()
    duplicate_count = sum(1 for _, t in q if t == normalized)
    q.append((now, normalized))
    return duplicate_count >= 2
