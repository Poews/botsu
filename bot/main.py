import logging
import os
import sys

from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from db import init_db
from handlers.admin import (
    ban_command,
    help_command,
    kick_command,
    mute_command,
    unban_command,
    unmute_command,
    unwarn_command,
    warn_command,
    warnings_command,
)
from handlers.moderation import handle_message
from handlers.stats import estadisticas_command
from handlers.personal import (
    borrarpersonal_command,
    catch_personal_command,
    personal_command,
    personales_command,
)
from handlers.settings import set_command, settings_command
from handlers.welcome import welcome_new_member

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    await init_db()
    logger.info("Database initialised")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # Help & info
    app.add_handler(CommandHandler("start",    help_command))
    app.add_handler(CommandHandler("help",     help_command))

    # Admin actions
    app.add_handler(CommandHandler("ban",      ban_command))
    app.add_handler(CommandHandler("unban",    unban_command))
    app.add_handler(CommandHandler("kick",     kick_command))
    app.add_handler(CommandHandler("mute",     mute_command))
    app.add_handler(CommandHandler("unmute",   unmute_command))
    app.add_handler(CommandHandler("warn",     warn_command))
    app.add_handler(CommandHandler("unwarn",   unwarn_command))
    app.add_handler(CommandHandler("warnings", warnings_command))

    # Settings
    app.add_handler(CommandHandler("settings",       settings_command))
    app.add_handler(CommandHandler("set",            set_command))

    # Stats
    app.add_handler(CommandHandler("estadisticas",   estadisticas_command))

    # Personal commands management
    app.add_handler(CommandHandler("personal",       personal_command))
    app.add_handler(CommandHandler("personales",     personales_command))
    app.add_handler(CommandHandler("borrarpersonal", borrarpersonal_command))

    # Welcome new members (requires "Chat Member" updates to be enabled)
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Auto-moderation on all group text messages
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND & filters.ChatType.GROUPS,
            handle_message,
        )
    )

    # Catch-all for personal commands (runs after all specific handlers, group=1)
    app.add_handler(
        MessageHandler(
            filters.COMMAND & filters.ChatType.GROUPS,
            catch_personal_command,
        ),
        group=1,
    )

    logger.info("Bot starting — polling for updates…")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "chat_member"],
    )


if __name__ == "__main__":
    main()
