import logging
from datetime import datetime, timezone
from db import get_settings

logger = logging.getLogger(__name__)

ICONS = {
    "BAN":             "🔨",
    "DESBAN":          "✅",
    "KICK":            "👢",
    "MUTE":            "🔇",
    "DESMUTE":         "🔊",
    "ADVERTENCIA":     "⚠️",
    "QUITAR WARN":     "🔄",
    "SPAM":            "🚫",
    "FLOOD":           "⏳",
    "LISTA NEGRA":     "🔕",
    "MUTE AUTO":       "✂️",
    "KICK ELIMINADOS": "🗑️",
    "VERIFICACIÓN":    "👤",
}


async def log_event(
    bot,
    chat_id: int,
    chat_title: str,
    action: str,
    target: str,
    target_id: int = None,
    admin: str = None,
    reason: str = None,
    extra: str = None,
):
    """Send a formatted moderation event to the configured log channel."""
    try:
        settings = await get_settings(chat_id)
        log_channel = settings.get("log_channel")
        if not log_channel:
            return

        icon = ICONS.get(action, "📋")
        now  = datetime.now(timezone.utc).strftime("%d/%m/%Y · %H:%M UTC")

        lines = [
            f"{icon} <b>─「 {action} 」</b>",
            "",
            f"👤 <b>Usuario:</b> {target}" + (f"  <code>{target_id}</code>" if target_id else ""),
            f"👮 <b>Admin:</b> {admin}" if admin else "🤖 <b>Acción automática</b>",
        ]
        if reason:
            lines.append(f"📝 <b>Razón:</b> {reason}")
        if extra:
            lines.append(f"ℹ️ {extra}")
        lines += [
            f"🏠 <b>Grupo:</b> {chat_title}",
            f"🕐 {now}",
        ]

        await bot.send_message(log_channel, "\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.warning("log_event error: %s", e)
