import re
import httpx

from telegram import Update
from telegram.ext import ContextTypes


async def bin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Debes indicar un BIN.\n\n"
            "Ejemplo:\n"
            "/bin 530691"
        )
        return

    bin_number = context.args[0].strip()

    # Aceptar únicamente BIN/IIN de 6 a 8 dígitos
    if not re.fullmatch(r"\d{6,8}", bin_number):
        await update.message.reply_text(
            "❌ BIN inválido.\n\n"
            "Debe contener entre 6 y 8 dígitos."
        )
        return

    url = f"https://lookup.binlist.net/{bin_number}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                headers={"Accept-Version": "3"},
            )

        if response.status_code == 404:
            await update.message.reply_text(
                f"❌ No encontré información para "
                f"<code>{bin_number}</code>.",
                parse_mode="HTML",
            )
            return

        if response.status_code != 200:
            await update.message.reply_text(
                "⚠️ El servicio de consulta no está disponible "
                "en este momento."
            )
            return

        data = response.json()

        scheme = data.get("scheme") or "Desconocida"
        card_type = data.get("type") or "Desconocido"
        brand = data.get("brand") or "Desconocida"

        bank = data.get("bank") or {}
        bank_name = bank.get("name") or "Desconocido"

        country = data.get("country") or {}
        country_name = country.get("name") or "Desconocido"
        country_emoji = country.get("emoji") or ""

        prepaid = data.get("prepaid")

        if prepaid is True:
            prepaid_text = "Sí"
        elif prepaid is False:
            prepaid_text = "No"
        else:
            prepaid_text = "Desconocido"

        result = (
            "💳 <b>Información del BIN</b>\n\n"
            f"🔢 <b>BIN:</b> <code>{bin_number}</code>\n"
            f"🏦 <b>Banco:</b> {bank_name}\n"
            f"💳 <b>Red:</b> {scheme}\n"
            f"🏷️ <b>Tipo:</b> {card_type}\n"
            f"📋 <b>Marca:</b> {brand}\n"
            f"🌎 <b>País:</b> {country_name} {country_emoji}\n"
            f"💰 <b>Prepago:</b> {prepaid_text}"
        )

        await update.message.reply_text(
            result,
            parse_mode="HTML",
        )

    except httpx.TimeoutException:
        await update.message.reply_text(
            "⏱️ La consulta tardó demasiado. Inténtalo nuevamente."
        )

    except httpx.RequestError:
        await update.message.reply_text(
            "❌ No pude conectarme al servicio de consulta."
        )

    except Exception:
        await update.message.reply_text(
            "❌ Ocurrió un error al consultar el BIN."
        )
