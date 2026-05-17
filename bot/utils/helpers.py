from telegram import Update, ChatMember
from telegram.ext import ContextTypes


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    if user_id is None:
        user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return False


async def get_target_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.mention_html()

    args = context.args
    if args:
        try:
            user_id = int(args[0])
            try:
                member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                return user_id, member.user.mention_html()
            except Exception:
                return user_id, f"User <code>{user_id}</code>"
        except ValueError:
            pass

    return None, None


def parse_duration(text: str) -> int:
    if not text:
        return 0
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    text = text.lower().strip()
    if text[-1] in multipliers:
        try:
            return int(text[:-1]) * multipliers[text[-1]]
        except ValueError:
            pass
    try:
        return int(text)
    except ValueError:
        return 0
