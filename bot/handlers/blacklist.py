import re
import logging
import aiosqlite
from db import DB_PATH, add_warning, get_settings, clear_warnings
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"warn", "mute", "delete"}


# ── DB helpers ────────────────────────────────────────────────────────────────

async def add_word(chat_id: int, word: str, action: str, added_by: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO blacklist (chat_id, word, action, added_by) VALUES (?, ?, ?, ?)",
                (chat_id, word.lower().strip(), action, added_by),
            )
            await db.commit()
            return True
        except Exception:
            return False  # UNIQUE constraint — word already exists


async def remove_word(chat_id: int, word: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM blacklist WHERE chat_id = ? AND word = ?",
            (chat_id, word.lower().strip()),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_words(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT word, action, added_at FROM blacklist WHERE chat_id = ? ORDER BY word",
            (chat_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_words_cached(chat_id: int) -> list[dict]:
    """Same as get_words but used by the message scanner."""
    return await get_words(chat_id)


async def clear_all_words(chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM blacklist WHERE chat_id = ?", (chat_id,))
        await db.commit()
        return cur.rowcount


# ── Detection ─────────────────────────────────────────────────────────────────

def _find_match(text: str, words: list[dict]) -> dict | None:
    """Return the first blacklist entry that matches the text, or None."""
    lower = text.lower()
    for entry in words:
        pattern = r"(?<!\w)" + re.escape(entry["word"]) + r"(?!\w)"
        if re.search(pattern, lower):
            return entry
    return None


async def check_blacklist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    """
    Called from handle_message. Checks text against the blacklist for this chat.
    Returns True if the message was acted upon (deleted), False otherwise.
    """
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    words = await get_all_words_cached(chat.id)
    if not words:
        return False

    match = _find_match(text, words)
    if not match:
        return False

    action = match["action"]
    word = match["word"]

    # Always delete the offending message
    try:
        await message.delete()
    except Exception:
        pass

    if action == "delete":
        try:
            await context.bot.send_message(
                chat.id,
                f"🚫 {user.mention_html()}, tu mensaje fue eliminado por contener una palabra no permitida.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif action == "warn":
        settings = await get_settings(chat.id)
        warn_limit = settings["warn_limit"]
        warn_count = await add_warning(chat.id, user.id, f'Palabra prohibida: "{word}"')

        if warn_count >= warn_limit:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                await clear_warnings(chat.id, user.id)
                await context.bot.send_message(
                    chat.id,
                    f"⛔ {user.mention_html()}, usaste una palabra no permitida y alcanzaste el límite de advertencias.\n"
                    f"🔨 Has sido <b>baneado automáticamente</b>.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Error en auto-ban por blacklist: %s", e)
        else:
            try:
                await context.bot.send_message(
                    chat.id,
                    f"⚠️ {user.mention_html()}, tu mensaje fue eliminado por contener una palabra no permitida.\n"
                    f"📊 Advertencias: <b>{warn_count}/{warn_limit}</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    elif action == "mute":
        import time
        try:
            until = int(time.time()) + 300  # 5 minutes
            await context.bot.restrict_chat_member(
                chat.id,
                user.id,
                ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await context.bot.send_message(
                chat.id,
                f"🔇 {user.mention_html()}, tu mensaje fue eliminado por contener una palabra no permitida.\n"
                f"Has sido silenciado por 5 minutos.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Error al silenciar por blacklist: %s", e)

    return True


# ── Command handlers ──────────────────────────────────────────────────────────

async def addpalabra_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addpalabra [palabra] [acción]
    Acción: warn (por defecto) | mute | delete
    """
    if not await is_admin(update, context):
        return

    chat = update.effective_chat

    if not context.args:
        await update.message.reply_text(
            "❌ Uso: <code>/addpalabra [palabra] [acción]</code>\n\n"
            "Acciones disponibles:\n"
            "• <b>warn</b> — elimina el mensaje y agrega una advertencia (por defecto)\n"
            "• <b>mute</b> — elimina el mensaje y silencia al usuario 5 minutos\n"
            "• <b>delete</b> — solo elimina el mensaje\n\n"
            "Ejemplo: <code>/addpalabra casino warn</code>",
            parse_mode="HTML",
        )
        return

    word = context.args[0].lower().strip()
    action = context.args[1].lower() if len(context.args) > 1 else "warn"

    if len(word) < 2:
        await update.message.reply_text("❌ La palabra debe tener al menos 2 caracteres.")
        return

    if action not in VALID_ACTIONS:
        await update.message.reply_text(
            f"❌ Acción inválida. Usa: <code>warn</code>, <code>mute</code> o <code>delete</code>.",
            parse_mode="HTML",
        )
        return

    added = await add_word(chat.id, word, action, update.effective_user.id)
    action_icons = {"warn": "⚠️", "mute": "🔇", "delete": "🗑️"}

    if added:
        await update.message.reply_text(
            f"✅ Palabra añadida a la lista negra.\n"
            f"🔤 Palabra: <code>{word}</code>\n"
            f"⚡ Acción: {action_icons[action]} <b>{action}</b>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"ℹ️ La palabra <code>{word}</code> ya está en la lista negra.",
            parse_mode="HTML",
        )


async def quitarpalabra_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quitarpalabra [palabra]"""
    if not await is_admin(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Uso: <code>/quitarpalabra [palabra]</code>",
            parse_mode="HTML",
        )
        return

    word = context.args[0].lower().strip()
    chat = update.effective_chat
    removed = await remove_word(chat.id, word)

    if removed:
        await update.message.reply_text(
            f"🗑️ Palabra <code>{word}</code> eliminada de la lista negra.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"❌ La palabra <code>{word}</code> no está en la lista negra.",
            parse_mode="HTML",
        )


async def palabras_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/palabras — lista todas las palabras prohibidas del grupo."""
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    words = await get_words(chat.id)

    if not words:
        await update.message.reply_text(
            "ℹ️ No hay palabras prohibidas en este grupo.\n\n"
            "Añade una con <code>/addpalabra [palabra]</code>.",
            parse_mode="HTML",
        )
        return

    action_icons = {"warn": "⚠️", "mute": "🔇", "delete": "🗑️"}
    lines = [f"🚫 <b>Palabras prohibidas — {chat.title}</b> ({len(words)} total)\n"]

    for w in words:
        icon = action_icons.get(w["action"], "❓")
        lines.append(f"• <code>{w['word']}</code> — {icon} {w['action']}")

    lines.append("\n<i>Usa /quitarpalabra [palabra] para eliminar una.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def limpiarpalabras_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/limpiarpalabras — borra toda la lista negra del grupo."""
    if not await is_admin(update, context):
        return

    chat = update.effective_chat
    count = await clear_all_words(chat.id)
    await update.message.reply_text(
        f"🗑️ Lista negra limpiada. Se eliminaron <b>{count}</b> palabra(s).",
        parse_mode="HTML",
    )
