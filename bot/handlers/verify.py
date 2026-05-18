import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# {user_id: set of chat_ids where the user is pending verification}
pending_users: dict[int, set] = {}

FULL_PERMISSIONS = ChatPermissions(
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
)

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

_CHECK_BTN = [[InlineKeyboardButton("✅ Ya me puse @usuario", callback_data="verify_check")]]


async def _unmute_pending(user, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Unmutes the user in all pending chats. Returns count of chats unmuted."""
    chat_ids = pending_users.pop(user.id, set())
    count = 0
    for chat_id in chat_ids:
        try:
            await context.bot.restrict_chat_member(chat_id, user.id, FULL_PERMISSIONS)
            await context.bot.send_message(
                chat_id,
                f"✅ {user.mention_html()} ya tiene <b>@{user.username}</b> "
                f"y ha sido habilitado para participar en el grupo.",
                parse_mode="HTML",
            )
            count += 1
        except Exception as e:
            logger.warning("Error al desmutear a %s en %s: %s", user.id, chat_id, e)
    return count


async def start_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles /start [verify_<chat_id>] sent from the inline button.
    If the user already has a username, unmutes them immediately.
    Otherwise shows instructions with a callback button.
    """
    user = update.effective_user
    args = context.args or []

    # Register which group they came from
    if args and args[0].startswith("verify_"):
        try:
            chat_id = int(args[0].split("_", 1)[1])
            pending_users.setdefault(user.id, set()).add(chat_id)
        except (ValueError, IndexError):
            pass

    if user.username:
        count = await _unmute_pending(user, context)
        msg = "✅ ¡Todo listo! Ya puedes participar en el grupo." if count else "✅ ¡Ya tienes @usuario! Todo bien."
        await update.message.reply_text(msg)
        return

    await update.message.reply_text(
        f"👋 Hola <b>{user.first_name}</b>.\n\n"
        f"⚠️ <b>Aún no tienes un @usuario</b> y por eso estás muteado en el grupo.\n\n"
        f"📱 Configúralo en:\n"
        f"<b>Ajustes → Editar perfil → Nombre de usuario</b>\n\n"
        f"Cuando lo hayas puesto, presiona el botón de abajo y te habilitamos al instante.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(_CHECK_BTN),
    )


async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the '✅ Ya me puse @usuario' inline button."""
    query = update.callback_query
    user  = query.from_user

    if user.username:
        count = await _unmute_pending(user, context)
        msg = (
            f"✅ ¡Perfecto, <b>@{user.username}</b>! Ya puedes participar en el grupo."
            if count else
            f"✅ ¡Todo en orden, <b>@{user.username}</b>!"
        )
        await query.edit_message_text(msg, parse_mode="HTML")
    else:
        await query.answer(
            "⚠️ Aún no tienes @usuario. Configúralo primero y vuelve a presionar.",
            show_alert=True,
        )
