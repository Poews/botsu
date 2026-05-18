import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def staff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/staff — muestra el equipo de administración del grupo con diseño casero."""
    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Este comando solo funciona en grupos.")
        return

    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.warning("Error al obtener admins: %s", e)
        await update.message.reply_text("❌ No pude obtener la lista de administradores.")
        return

    owner   = None
    members = []

    for admin in admins:
        if admin.user.is_bot:
            continue
        name = f"@{admin.user.username}" if admin.user.username else admin.user.full_name
        title = getattr(admin, "custom_title", None)
        if admin.status == "creator":
            owner = (name, title)
        else:
            members.append((name, title))

    # ── Build message ─────────────────────────────────────────────────────────
    lines = [
        f"🏠 <b>━━━「 STAFF 」━━━</b> 🏠",
        f"",
        f"     🏡 <b>{chat.title}</b>",
        f"",
    ]

    if owner:
        name, title = owner
        label = f" · <i>{title}</i>" if title else ""
        lines += [
            f"👑 <b>DUEÑO</b>",
            f"   └ {name}{label}",
            f"",
        ]

    if members:
        lines.append(f"🛡️ <b>ADMINISTRADORES</b>")
        for i, (name, title) in enumerate(members):
            label  = f" · <i>{title}</i>" if title else ""
            prefix = "└" if i == len(members) - 1 else "├"
            lines.append(f"   {prefix} {name}{label}")
        lines.append("")

    lines += [
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
        f"🔒 <i>El equipo vela por el orden</i>",
        f"<i>y el buen ambiente del grupo.</i>",
    ]

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
