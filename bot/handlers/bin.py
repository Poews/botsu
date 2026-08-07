import re
import httpx
from telegram import Update
from telegram.ext import ContextTypes


async def bin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "❌ Uso correcto:\n/bin 522416"
        )
        return

    bin_number = context.args[0].strip()

    if not re.fullmatch(r"\d{6,8}", bin_number):
        await update.message.reply_text(
            "❌ BIN inválido.\n\n"
            "Usa solamente 6 a 8 dígitos.\n"
            "Ejemplo: /bin 522416"
        )
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://lookup.binlist.net/{bin_number}",
                headers={
                    "Accept-Version": "3",
                    "User-Agent": "Bot/1.0"
                }
            )

        if response.status_code != 200:
            await update.message.reply_text(
                f"❌ No se encontraron datos para {bin_number}."
            )
            return

        data = response.json()

        # DATOS DEL BIN
        scheme = data.get("scheme") or "UNKNOWN"
        card_type = data.get("type") or "UNKNOWN"

        # En BINLIST, 'brand' contiene cosas como
        # PREPAID RELOADABLE
        level = data.get("brand") or "UNKNOWN"

        bank = data.get("bank") or {}
        bank_name = bank.get("name") or "UNKNOWN"

        country = data.get("country") or {}
        country_name = country.get("name") or "UNKNOWN"
        country_code = country.get("alpha2") or ""

        # BANDERA
        flag = ""

        if len(country_code) == 2:
            flag = "".join(
                chr(127397 + ord(letter))
                for letter in country_code.upper()
            )

        # =====================================================
        # DISEÑO
        # =====================================================

        message = (
            f"📄 <b>Resultados para {bin_number}:</b>\n\n"
            f"• ✅ <b>BIN:</b> <code>{bin_number}</code>\n"
            f"• 💳 <b>Brand:</b> {scheme.upper()}\n"
            f"• 💰 <b>Type:</b> {card_type.title()}\n"
            f"• 📊 <b>Level:</b> {level.upper()}\n"
            f"• 🏦 <b>Bank:</b> {bank_name.upper()}\n"
            f"• 🌎 <b>Country:</b> {flag} {country_name} {flag}\n\n"
            f"<code>{bin_number} / {scheme.upper()} - "
            f"{card_type.title()} - {level.upper()} / "
            f"{bank_name.upper()} - {country_name.upper()} "
            f"[{country_code.upper()}]</code>"
        )

        await update.message.reply_text(
            message,
            parse_mode="HTML"
        )

    except httpx.TimeoutException:
        await update.message.reply_text(
            "⏳ La consulta tardó demasiado. Inténtalo nuevamente."
        )

    except Exception as e:
        print(f"Error en /bin: {e}")

        await update.message.reply_text(
            "❌ Ocurrió un error al consultar el BIN."
        )
