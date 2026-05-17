import logging
import aiosqlite
from db import DB_PATH
from telegram import Update, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

# Cooldown to prevent report spam: {(chat_id, user_id): timestamp}
_cooldowns: dict = {}
COOLDOWN_SECONDS = 60


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _save_report(
    chat_id: int,
    reporter_id: int,
    reporter_name: str,
    reported_user_id: int | None,
    reported_name: str | None,
    message_text: str | None,
    reason: str | None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO reports
               (chat_id, reporter_id, reporter_name, reported_user_id, reported_name, message_text, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, reporter_id, reporter_name, reported_user_id, reported_name, message_text, reason),
        )
        await db.commit()


async def _get_reports(chat_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM reports WHERE chat_id = ?
               ORDER BY reported_at DESC LIMIT ?""",
            (chat_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _display_name(user) -> str:
    name = " ".join(p for p in [user.first_name or "", user.last_name or ""] if p).strip()
    return name or str(user.id)


def _is_on_cooldown(chat_id: int, user_id: int) -> int:
    """Returns remaining cooldown seconds, or 0 if not on cooldown."""
    import time
    key = (chat_id, user_id)
    last = _cooldowns.get(key, 0)
    remaining = int(COOLDOWN_SECONDS - (time.time() - last))
    return remaining if remaining > 0 else 0


def _set_cooldown(chat_id: int, user_id: int):
    import time
    _cooldowns[(chat_id, user_id)] = time.time()


# ── Command handlers ──────────────────────────────────────────────────────────

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /report [razón]  — responde a un mensaje para reportarlo a los admins.
    Cualquier miembro del grupo puede usarlo.
    """
    message = update.effective_message
    reporter = update.effective_user
    chat = update.effective_chat

    if not message or not reporter or not chat:
        return

    # Must be used in a group
    if chat.type not in ("group", "supergroup"):
        await message.reply_text("❌ Este comando solo funciona en grupos.")
        return

    # Must reply to a message
    if not message.reply_to_message:
        await message.reply_text(
            "ℹ️ <b>¿Cómo reportar?</b>\n\n"
            "Responde al mensaje que quieres reportar y escribe:\n"
            "<code>/report [razón opcional]</code>",
            parse_mode="HTML",
        )
        return

    reported_msg = message.reply_to_message
    reported_user = reported_msg.from_user

    # Can't report admins or bots
    if reported_user:
        if reported_user.is_bot:
            await message.reply_text("❌ No puedes reportar a un bot.")
            return
        if await is_admin(update, context, user_id=reported_user.id):
            await message.reply_text("❌ No puedes reportar a un administrador.")
            return

    # Cooldown check
    remaining = _is_on_cooldown(chat.id, reporter.id)
    if remaining:
        await message.reply_text(
            f"⏳ Ya enviaste un reporte recientemente. Espera {remaining} segundos."
        )
        return

    _set_cooldown(chat.id, reporter.id)

    reason = " ".join(context.args) if context.args else None
    reported_text = reported_msg.text or reported_msg.caption or "(sin texto)"
    reported_name = _display_name(reported_user) if reported_user else "Desconocido"
    reporter_name = _display_name(reporter)

    # Save to DB
    await _save_report(
        chat.id,
        reporter.id,
        reporter_name,
        reported_user.id if reported_user else None,
        reported_name,
        reported_text[:500],
        reason,
    )

    # Build admin notification
    reason_line = f"\n📝 <b>Razón:</b> {reason}" if reason else ""
    preview = reported_text[:200] + ("…" if len(reported_text) > 200 else "")

    notification = (
        f"🚨 <b>Nuevo reporte en {chat.title}</b>\n\n"
        f"👤 <b>Reportado por:</b> {reporter.mention_html()}\n"
        f"🎯 <b>Usuario reportado:</b> {reported_user.mention_html() if reported_user else reported_name}"
        f"{reason_line}\n\n"
        f"💬 <b>Mensaje:</b>\n<blockquote>{preview}</blockquote>"
    )

    # Button linking to the reported message (only works in supergroups with username)
    keyboard = None
    if chat.username:
        url = f"https://t.me/{chat.username}/{reported_msg.message_id}"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📌 Ver mensaje", url=url)]]
        )

    # Notify all admins via private message
    admins_notified = 0
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        for admin in admins:
            if admin.user.is_bot:
                continue
            try:
                await context.bot.send_message(
                    admin.user.id,
                    notification,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                admins_notified += 1
            except Exception:
                # Admin hasn't started the bot in private — skip silently
                pass
    except Exception as e:
        logger.warning("Error al obtener administradores: %s", e)

    # Confirm to the reporter (then delete both messages after a moment)
    try:
        confirm = await message.reply_text(
            f"✅ Reporte enviado. Los administradores han sido notificados.",
        )
        # Delete the /report command and confirmation after 5 seconds
        context.job_queue.run_once(
            _delete_messages,
            5,
            data={"chat_id": chat.id, "msg_ids": [message.message_id, confirm.message_id]},
        )
    except Exception as e:
        logger.warning("Error al confirmar reporte: %s", e)


async def _delete_messages(context):
    data = context.job.data
    for msg_id in data["msg_ids"]:
        try:
            await context.bot.delete_message(data["chat_id"], msg_id)
        except Exception:
            pass


async def reportes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reportes — muestra los últimos reportes del grupo (solo admins).
    """
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    reports = await _get_reports(chat.id, limit=10)

    if not reports:
        await update.message.reply_text(
            "ℹ️ No hay reportes registrados en este grupo.",
        )
        return

    lines = [f"🚨 <b>Últimos reportes — {chat.title}</b>\n"]
    for r in reports:
        date = str(r["reported_at"])[:16]
        reason = f" — {r['reason']}" if r["reason"] else ""
        lines.append(
            f"• <b>{r['reported_name'] or 'Desconocido'}</b> "
            f"reportado por <b>{r['reporter_name']}</b>{reason} "
            f"<i>({date})</i>"
        )

    lines.append(f"\n<i>Total registrado: {len(reports)} reporte(s)</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
