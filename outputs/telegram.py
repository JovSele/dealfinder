# outputs/telegram.py — Telegram alerting
#
# Rozhranie: send_alert(listing, score) → None
# Všetky output moduly musia implementovať toto rozhranie.
#
# Free kanál: send_free_alert(listing, score) → None
# Posiela s ⏰ badge a informáciou o oneskorení.

import requests

import config


def send_alert(listing: dict, score: dict | None = None) -> None:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        _log("TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID nie je nastavený — preskakujem")
        return

    text = _format_message(listing, score)
    _send(config.TELEGRAM_CHAT_ID, text)


def send_free_alert(listing: dict, score: dict | None = None) -> None:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_FREE_CHAT_ID:
        _log("TELEGRAM_FREE_CHAT_ID nie je nastavený — preskakujem free alert")
        return

    text = _format_message(listing, score, free_delay=True)
    _send(config.TELEGRAM_FREE_CHAT_ID, text)


# ── Interné ───────────────────────────────────────────────────

def _currency(listing: dict) -> str:
    """CZK pre Sreality, EUR pre všetko ostatné."""
    return "Kč" if listing.get("source", "").startswith("sreality") else "€"


def _fmt_price(value: int | float, currency: str) -> str:
    """Formátuj cenu s medzerou ako oddeľovačom tisícov."""
    return f"{int(value):,}".replace(",", " ") + f" {currency}"


def _send(chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            _log(f"Alert odoslaný (chat {chat_id}): {text[:50]}")
        else:
            _log(f"Telegram API chyba {r.status_code}: {r.text[:100]}")
    except requests.RequestException as e:
        _log(f"Sieťová chyba: {e}")


def _format_message(listing: dict, score: dict | None, free_delay: bool = False) -> str:
    currency = _currency(listing)
    lines = []

    # Hlavička
    if free_delay:
        lines.append(f"⏰ *-{config.FREE_DELAY_HOURS}h delay* | DEALFINDER FREE")
        lines.append("")

    if score and score["pct_below"] >= 10:
        lines.append(f"🔥 *DEAL: {score['label']}*")
    else:
        lines.append("🏠 *Nový inzerát*")

    lines.append("")
    lines.append(f"*{listing['title']}*")

    # Cena
    price = listing.get("price", 0)
    if price:
        lines.append(f"💰 {_fmt_price(price, currency)}")
    else:
        lines.append("💰 Cena neuvedená")

    # Plocha
    area = listing.get("area_m2", 0)
    if area:
        lines.append(f"📐 {area} m²")

    # Deal Score detail
    if score:
        lines.append(
            f"📊 {_fmt_price(score['price_per_m2'], currency)}/m²"
            f" vs priemer {_fmt_price(score['avg_per_m2'], currency)}/m²"
        )

    # Lokalita
    loc = listing.get("locality", "")
    if loc:
        lines.append(f"📍 {loc}")

    # Zdroj
    lines.append(f"🔗 [{listing['source']}]({listing['url']})")

    # Free upgrade hint
    if free_delay:
        lines.append("")
        lines.append("_Chceš alerty okamžite? → dealfinder.sk_")

    return "\n".join(lines)


def _log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [telegram] {msg}")