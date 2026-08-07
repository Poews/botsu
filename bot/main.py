import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from db import init_db
from handlers.bin import bin_command
from handlers.admin import (
    admin_command,
    all_command,
    ban_command,
    cmds_command,
    free_command,
    help_command,
    id_command,
    kick_command,
    kickdeleted_command,
    mod_command,
    mute_command,
    reload_command,
    say_command,
    unadmin_command,
    unban_command,
    unfree_command,
    unmod_command,
    unmute_command,
    unwarn_command,
    warn_command,
    warnings_command,
)
from handlers.moderation import handle_message
from handlers.stats import estadisticas_command
from handlers.report import report_command, reportes_command
from handlers.notes import nota_command, notas_command, borrarnota_command
from handlers.blacklist import (
    addpalabra_command,
    quitarpalabra_command,
    palabras_command,
    limpiarpalabras_command,
)
from handlers.personal import (
    borrarpersonal_command,
    catch_personal_command,
    personal_command,
    personales_command,
)
from handlers.settings import set_command, settings_command
from handlers.staff import staff_command
from handlers.verify import start_verify, verify_callback
from handlers.welcome import welcome_new_member


# =========================================================
# SERVIDOR HTTP PARA RENDER / UPTIMEROBOT
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot is online")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        # Evita llenar los logs de Render con cada comprobación de UptimeRobot
        return


def start_health_server():
    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(("0.0.0.0", port), HealthHandler)

    logger.info(f"Health server running on port {port}")

    server.serve_forever()


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


# =========================================================
# DATABASE
# =========================================================

async def post_init(app: Application) -> None:
    await init_db()
    logger.info("Database initialised")


# =========================================================
# BOT
# =========================================================

def main() -> None:

    # Iniciar servidor HTTP para Render/UptimeRobot
    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )
    health_thread.start()

    # Token del bot
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
    # Help & info
app.add_handler(CommandHandler("start", start_verify))
app.add_handler(CommandHandler("bin", bin_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cmds", cmds_command))
    app.add_handler(CommandHandler("reload", reload_command))

    # BIN lookup
    app.add_handler(CommandHandler("bin", bin_command))

    # Username verification callback
    app.add_handler(
        CallbackQueryHandler(
            verify_callback,
            pattern="^verify_check$"
        )
    )

    # Say (send as bot)
    app.add_handler(CommandHandler("say", say_command))

    # Clean deleted accounts
    app.add_handler(
        CommandHandler(
            "kickdeleted",
            kickdeleted_command
        )
    )

    # Free pass
    app.add_handler(CommandHandler("free", free_command))
    app.add_handler(CommandHandler("unfree", unfree_command))

    # ID info
    app.add_handler(CommandHandler("id", id_command))

    # Mention all
    app.add_handler(CommandHandler("all", all_command))

    # Roles
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("unadmin", unadmin_command))
    app.add_handler(CommandHandler("mod", mod_command))
    app.add_handler(CommandHandler("unmod", unmod_command))

    # Staff list
    app.add_handler(CommandHandler("staff", staff_command))

    # Admin actions
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("unwarn", unwarn_command))
    app.add_handler(CommandHandler("warnings", warnings_command))

    # Settings
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("set", set_command))

    # Stats
    app.add_handler(
        CommandHandler(
            "estadisticas",
            estadisticas_command
        )
    )

    # Reports
    app.add_handler(
        CommandHandler(
            "report",
            report_command
        )
    )

    app.add_handler(
        CommandHandler(
            "reportes",
            reportes_command
        )
    )

    # Notes
    app.add_handler(
        CommandHandler(
            "nota",
            nota_command
        )
    )

    app.add_handler(
        CommandHandler(
            "notas",
            notas_command
        )
    )

    app.add_handler(
        CommandHandler(
            "borrarnota",
            borrarnota_command
        )
    )

    # Blacklist
    app.add_handler(
        CommandHandler(
            "addpalabra",
            addpalabra_command
        )
    )

    app.add_handler(
        CommandHandler(
            "quitarpalabra",
            quitarpalabra_command
        )
    )

    app.add_handler(
        CommandHandler(
            "palabras",
            palabras_command
        )
    )

    app.add_handler(
        CommandHandler(
            "limpiarpalabras",
            limpiarpalabras_command
        )
    )

    # Personal commands management
    app.add_handler(
        CommandHandler(
            "personal",
            personal_command
        )
    )

    app.add_handler(
        CommandHandler(
            "personales",
            personales_command
        )
    )

    app.add_handler(
        CommandHandler(
            "borrarpersonal",
            borrarpersonal_command
        )
    )

    # Welcome new members
    app.add_handler(
        ChatMemberHandler(
            welcome_new_member,
            ChatMemberHandler.CHAT_MEMBER
        )
    )

    # Auto-moderation on all group text messages
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION)
            & ~filters.COMMAND
            & filters.ChatType.GROUPS,
            handle_message,
        )
    )

    # Catch-all for personal commands
    app.add_handler(
        MessageHandler(
            filters.COMMAND
            & filters.ChatType.GROUPS,
            catch_personal_command,
        ),
        group=1,
    )

    logger.info("Bot starting — polling for updates…")

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "chat_member",
            "callback_query"
        ],
    )


if __name__ == "__main__":
    main()
