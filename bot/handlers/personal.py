import logging
import aiosqlite
from db import DB_PATH
from telegram import Update
from telegram.ext import ContextTypes
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

# Reserved command names that cannot be used as personal commands
RESERVED = {
    "start", "help", "ban", "unban", "kick", "mute", "unmute",
    "warn", "unwarn", "warnings", "settings", "set",
    "personal", "personales", "borrarpersonal",
}


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _save_command(chat_id: int, name: str, content: str, created_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO personal_commands (chat_id, command_name, content, created_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id, command_name) DO UPDATE SET content = excluded.content,
               created_by = excluded.created_by,
               created_at = CURRENT_TIMESTAMP""",
            (chat_id, name.lower(), content, created_by),
        )
        await db.commit()


async def _get_command(chat_id: int, name: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT content FROM personal_commands WHERE chat_id = ? AND command_name = ?",
            (chat_id, name.lower()),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def _list_commands(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT command_name, created_at FROM personal_commands WHERE chat_id = ? ORDER BY command_name",
            (chat_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def _delete_command(chat_id: int, name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM personal_commands WHERE chat_id = ? AND command_name = ?",
            (chat_id, name.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


# ── Command handlers ──────────────────────────────────────────────────────────

async def personal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /personal [nombre]  — responde a un mensaje para guardarlo con ese nombre.
    Uso posterior: /nombre  → el bot enviará el texto guardado.
    """
    if not await is_admin(update, context):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not context.args:
        await message.reply_text(
            "❌ Uso: <b>/personal [nombre]</b> respondiendo al mensaje que quieres guardar.\n\n"
            "Ejemplo:\n"
            "  Responde a un mensaje y escribe: <code>/personal reglas</code>\n"
            "  Luego usa <code>/reglas</code> para que el bot lo envíe.",
            parse_mode="HTML",
        )
        return

    name = context.args[0].lower().strip()

    if name in RESERVED:
        await message.reply_text(
            f"❌ <b>/{name}</b> es un comando reservado y no puede usarse.",
            parse_mode="HTML",
        )
        return

    if not name.isalnum() or len(name) > 32:
        await message.reply_text(
            "❌ El nombre solo puede contener letras y números, y tener máximo 32 caracteres."
        )
        return

    if not message.reply_to_message:
        await message.reply_text(
            "❌ Debes <b>responder</b> a un mensaje para guardarlo.",
            parse_mode="HTML",
        )
        return

    replied = message.reply_to_message
    content = replied.text or replied.caption

    if not content:
        await message.reply_text(
            "❌ Solo se pueden guardar mensajes de texto."
        )
        return

    await _save_command(chat.id, name, content, user.id)

    await message.reply_text(
        f"✅ Comando personal guardado.\n"
        f"📌 Usa <code>/{name}</code> para enviarlo en el grupo.",
        parse_mode="HTML",
    )


async def personales_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /personales — lista todos los comandos personales guardados en el grupo.
    """
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    commands = await _list_commands(chat.id)

    if not commands:
        await update.message.reply_text(
            "ℹ️ No hay comandos personales guardados en este grupo.\n\n"
            "Crea uno con <b>/personal [nombre]</b> respondiendo a un mensaje.",
            parse_mode="HTML",
        )
        return

    lines = [f"📋 <b>Comandos personales — {chat.title}</b>\n"]
    for cmd in commands:
        lines.append(f"• <code>/{cmd['command_name']}</code>  <i>({cmd['created_at'][:10]})</i>")
    lines.append(f"\n<i>Total: {len(commands)} comando(s)</i>")
    lines.append("Usa <code>/borrarpersonal [nombre]</code> para eliminar uno.")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def borrarpersonal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /borrarpersonal [nombre] — elimina un comando personal guardado.
    """
    if not await is_admin(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Uso: <code>/borrarpersonal [nombre]</code>",
            parse_mode="HTML",
        )
        return

    name = context.args[0].lower().strip()
    chat = update.effective_chat
    deleted = await _delete_command(chat.id, name)

    if deleted:
        await update.message.reply_text(
            f"🗑️ Comando <code>/{name}</code> eliminado correctamente.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"❌ No existe ningún comando personal llamado <code>/{name}</code>.",
            parse_mode="HTML",
        )


async def catch_personal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Captura cualquier comando desconocido y comprueba si coincide con un comando personal.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    raw = message.text or ""
    if not raw.startswith("/"):
        return

    # Extract the command name (strip leading / and any @botname suffix)
    cmd_part = raw.split()[0][1:]
    if "@" in cmd_part:
        cmd_part = cmd_part.split("@")[0]
    cmd_part = cmd_part.lower()

    content = await _get_command(chat.id, cmd_part)
    if content:
        await message.reply_text(content)
