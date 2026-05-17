import time
import re
import logging
from collections import defaultdict, deque
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from db import get_settings
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

flood_tracker: dict = defaultdict(deque)
spam_tracker: dict = defaultdict(deque)

URL_PATTERN = re.compile(
    r"(https?://[^\s]+|www\.[^\s]+|t\.me/[^\s]+)",
    re.IGNORECASE,
)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if await is_admin(update, context):
        return

    settings = await get_settings(chat.id)
    text = message.text or message.caption or ""

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
                    f"⚠️ {user.mention_html()} is sending messages too fast and has been muted for 1 minute.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Mute flooder failed: %s", e)
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
                    f"🚫 {user.mention_html()}, duplicate message detected and deleted.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Spam notice failed: %s", e)
            return

    if settings["max_message_length"] and len(text) > settings["max_message_length"]:
        try:
            await message.delete()
            await context.bot.send_message(
                chat.id,
                f"✂️ {user.mention_html()}, your message was deleted — it exceeded the "
                f"{settings['max_message_length']}-character limit.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Delete long message failed: %s", e)
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
                f"🔗 {user.mention_html()}, links are not allowed in this group.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Delete link message failed: %s", e)
        return


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
