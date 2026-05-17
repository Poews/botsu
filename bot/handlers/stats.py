import logging
import aiosqlite
from db import DB_PATH
from telegram import Update
from telegram.ext import ContextTypes
from utils.helpers import is_admin, get_target_from_message

logger = logging.getLogger(__name__)


# ── DB helpers ────────────────────────────────────────────────────────────────

async def increment_stat(chat_id: int, user_id: int, user_name: str, field: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"""INSERT INTO user_stats (chat_id, user_id, user_name, {field}, last_seen)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    {field} = {field} + 1,
                    user_name = excluded.user_name,
                    last_seen = CURRENT_TIMESTAMP""",
            (chat_id, user_id, user_name),
        )
        await db.commit()


async def get_user_stats(chat_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, COUNT(w.id) as warnings
               FROM user_stats s
               LEFT JOIN warnings w ON w.chat_id = s.chat_id AND w.user_id = s.user_id
               WHERE s.chat_id = ? AND s.user_id = ?
               GROUP BY s.chat_id, s.user_id""",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_top_active(chat_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_name, user_id, messages, spam, floods, mutes
               FROM user_stats
               WHERE chat_id = ? AND messages > 0
               ORDER BY messages DESC
               LIMIT ?""",
            (chat_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_top_offenders(chat_id: int, limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.user_name, s.user_id, s.spam, s.floods, s.mutes,
                      COUNT(w.id) as warnings
               FROM user_stats s
               LEFT JOIN warnings w ON w.chat_id = s.chat_id AND w.user_id = s.user_id
               WHERE s.chat_id = ?
               GROUP BY s.user_id
               HAVING (s.spam + s.floods + s.mutes + warnings) > 0
               ORDER BY (s.spam + s.floods + s.mutes + warnings) DESC
               LIMIT ?""",
            (chat_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Command handler ───────────────────────────────────────────────────────────

async def estadisticas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    message = update.effective_message

    # If replying to a user or passing an ID → show individual stats
    user_id, mention = await get_target_from_message(update, context)
    if user_id:
        row = await get_user_stats(chat.id, user_id)
        if not row:
            await message.reply_text(
                f"ℹ️ No hay estadísticas registradas para {mention}.",
                parse_mode="HTML",
            )
            return

        name = row.get("user_name") or mention
        text = (
            f"📊 <b>Estadísticas de {mention}</b>\n\n"
            f"💬 Mensajes enviados:   <b>{row['messages']}</b>\n"
            f"⚠️ Advertencias:        <b>{row['warnings']}</b>\n"
            f"🔇 Silenciados:         <b>{row['mutes']}</b>\n"
            f"🌊 Floods detectados:   <b>{row['floods']}</b>\n"
            f"🚫 Spam detectado:      <b>{row['spam']}</b>\n"
            f"🕐 Último mensaje:      <i>{str(row['last_seen'])[:16]}</i>"
        )
        await message.reply_text(text, parse_mode="HTML")
        return

    # No target → show group summary
    active = await get_top_active(chat.id, limit=10)
    offenders = await get_top_offenders(chat.id, limit=5)

    lines = [f"📊 <b>Estadísticas del grupo — {chat.title}</b>\n"]

    if active:
        lines.append("🏆 <b>Más activos</b>")
        for i, u in enumerate(active, 1):
            name = u["user_name"] or f"ID {u['user_id']}"
            lines.append(f"  {i}. {name} — <b>{u['messages']}</b> mensajes")
    else:
        lines.append("ℹ️ Aún no hay mensajes registrados.")

    if offenders:
        lines.append("\n⚠️ <b>Más infracciones</b>")
        for u in offenders:
            name = u["user_name"] or f"ID {u['user_id']}"
            parts = []
            if u["warnings"]: parts.append(f"⚠️ {u['warnings']} advert.")
            if u["mutes"]:    parts.append(f"🔇 {u['mutes']} silenc.")
            if u["floods"]:   parts.append(f"🌊 {u['floods']} floods")
            if u["spam"]:     parts.append(f"🚫 {u['spam']} spam")
            lines.append(f"  • {name}: {', '.join(parts)}")

    lines.append(
        "\n<i>Usa /estadisticas respondiendo a un mensaje para ver estadísticas individuales.</i>"
    )
    await message.reply_text("\n".join(lines), parse_mode="HTML")
