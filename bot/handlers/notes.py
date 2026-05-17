import logging
import aiosqlite
from db import DB_PATH
from telegram import Update
from telegram.ext import ContextTypes
from utils.helpers import is_admin, get_target_from_message

logger = logging.getLogger(__name__)


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _add_note(
    chat_id: int,
    user_id: int,
    user_name: str,
    note_text: str,
    added_by: int,
    added_by_name: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO notes (chat_id, user_id, user_name, note_text, added_by, added_by_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, user_id, user_name, note_text, added_by, added_by_name),
        )
        await db.commit()
        return cur.lastrowid


async def _get_notes(chat_id: int, user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM notes WHERE chat_id = ? AND user_id = ?
               ORDER BY added_at DESC""",
            (chat_id, user_id),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def _delete_note(note_id: int, chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM notes WHERE id = ? AND chat_id = ?",
            (note_id, chat_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def _delete_all_notes(chat_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM notes WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()
        return cur.rowcount


# ── Helpers ───────────────────────────────────────────────────────────────────

def _display_name(user) -> str:
    name = " ".join(p for p in [user.first_name or "", user.last_name or ""] if p).strip()
    return name or str(user.id)


# ── Command handlers ──────────────────────────────────────────────────────────

async def nota_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nota [reply/@id] [texto]  — guarda una nota privada sobre un usuario.
    Solo visible para admins. Útil para historial de comportamiento.
    """
    if not await is_admin(update, context):
        return

    message = update.effective_message
    chat = update.effective_chat
    admin = update.effective_user
    args = context.args or []

    user_id, mention = await get_target_from_message(update, context)

    if not user_id:
        await message.reply_text(
            "❌ Uso: <b>/nota</b> respondiendo a un mensaje, seguido del texto.\n\n"
            "Ejemplo:\n<code>/nota historial sospechoso, enviaba spam</code>",
            parse_mode="HTML",
        )
        return

    # Extract note text (everything after the command, minus the ID arg if not a reply)
    if message.reply_to_message:
        note_text = " ".join(args).strip()
    else:
        note_text = " ".join(args[1:]).strip()

    if not note_text:
        await message.reply_text(
            "❌ Escribe el texto de la nota después del comando.\n"
            "Ejemplo: <code>/nota comportamiento agresivo el día de hoy</code>",
            parse_mode="HTML",
        )
        return

    # Resolve target name
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        user_name = _display_name(member.user)
    except Exception:
        user_name = f"Usuario {user_id}"

    note_id = await _add_note(
        chat.id,
        user_id,
        user_name,
        note_text,
        admin.id,
        _display_name(admin),
    )

    await message.reply_text(
        f"📝 Nota guardada (ID #{note_id}).\n"
        f"👤 Usuario: {mention}\n"
        f"📄 Nota: <i>{note_text}</i>",
        parse_mode="HTML",
    )


async def notas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /notas [reply/@id]  — muestra todas las notas de un usuario (solo admins).
    """
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    user_id, mention = await get_target_from_message(update, context)

    if not user_id:
        await update.message.reply_text(
            "❌ Responde a un mensaje o proporciona un ID de usuario.",
        )
        return

    notes = await _get_notes(chat.id, user_id)

    if not notes:
        await update.message.reply_text(
            f"ℹ️ No hay notas registradas para {mention}.",
            parse_mode="HTML",
        )
        return

    lines = [f"📋 <b>Notas sobre {mention}</b> ({len(notes)} total)\n"]
    for n in notes:
        date = str(n["added_at"])[:16]
        lines.append(
            f"<b>#{n['id']}</b> — <i>{date}</i> (por {n['added_by_name']})\n"
            f"   📄 {n['note_text']}\n"
        )
    lines.append("<i>Usa /borrarnota [ID] para eliminar una nota específica.</i>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def borrarnota_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /borrarnota [ID]  — elimina una nota por su ID numérico.
    """
    if not await is_admin(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Uso: <code>/borrarnota [ID]</code>\n"
            "El ID lo ves al usar /notas.",
            parse_mode="HTML",
        )
        return

    try:
        note_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ El ID debe ser un número.")
        return

    chat = update.effective_chat
    deleted = await _delete_note(note_id, chat.id)

    if deleted:
        await update.message.reply_text(
            f"🗑️ Nota <b>#{note_id}</b> eliminada correctamente.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"❌ No se encontró la nota #{note_id} en este grupo.",
        )
