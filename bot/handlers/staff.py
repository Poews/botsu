import logging
from telegram import Update
from telegram.ext import ContextTypes

from db import get_all_staff

logger = logging.getLogger(__name__)


async def staff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/staff — muestra el equipo de administración del grupo con diseño casero."""
    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Este comando solo funciona en grupos.")
        return

    try:
        tg_admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.warning("Error al obtener admins: %s", e)
        await update.message.reply_text("❌ No pude obtener la lista de administradores.")
        return

    # Telegram admins
    owner   = None
    tg_members = []
    for admin in tg_admins:
        if admin.user.is_bot:
            continue
        name  = f"@{admin.user.username}" if admin.user.username else admin.user.full_name
        title = getattr(admin, "custom_title", None)
        if admin.status == "creator":
            owner = (name, title)
        else:
            tg_members.append((name, title))

    # Custom DB roles
    db_staff = await get_all_staff(chat.id)
    db_admins = []
    db_mods   = []
    tg_ids    = {a.user.id for a in tg_admins}
    for s in db_staff:
        if s["user_id"] in tg_ids:
            continue  # already shown in TG list
        label = f"@{s['username']}" if s["username"] else f"<code>{s['user_id']}</code>"
        if s["role"] == "admin":
            db_admins.append(label)
        else:
            db_mods.append(label)

    # ── Build message ──────────────────────────────────────────────────────────
    lines = [
        "🏠 <b>━━━「 STAFF 」━━━</b> 🏠",
        "",
        f"     🏡 <b>{chat.title}</b>",
        "",
    ]

    if owner:
        name, title = owner
        label = f" · <i>{title}</i>" if title else ""
        lines += [
            "👑 <b>DUEÑO</b>",
            f"   └ {name}{label}",
            "",
        ]

    all_admins = [(n, t) for n, t in tg_members] + [(n, None) for n in db_admins]
    if all_admins:
        lines.append("🛡️ <b>ADMINISTRADORES</b>")
        for i, (name, title) in enumerate(all_admins):
            label  = f" · <i>{title}</i>" if title else ""
            prefix = "└" if i == len(all_admins) - 1 else "├"
            lines.append(f"   {prefix} {name}{label}")
        lines.append("")

    if db_mods:
        lines.append("⚔️ <b>MODERADORES</b>")
        for i, name in enumerate(db_mods):
            prefix = "└" if i == len(db_mods) - 1 else "├"
            lines.append(f"   {prefix} {name}")
        lines.append("")

    lines += [
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
        "🔒 <i>El equipo vela por el orden</i>",
        "<i>y el buen ambiente del grupo.</i>",
    ]

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
