# outputs/telegram.py — Telegram alerting
#
# Rozhranie: send_alert(listing, score) → None
# Všetky output moduly musia implementovať toto rozhranie.

import requests

import config


def send_alert(listing: dict, score: dict | None = None) -> None:
    """Pošli Telegram správu o novom inzeráte.

    Args:
        listing: inzerát dict (z BaseScraper)
        score:   Deal Score dict (z deal_score.score()) alebo None
    """
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        _log("TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID nie je nastavený — preskakujem")
        return

    text = _format_message(listing, score)

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  config.TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": False,
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            _log(f"Alert odoslaný: {listing['title'][:50]}")
        else:
            _log(f"Telegram API chyba {r.status_code}: {r.text[:100]}")
    except requests.RequestException as e:
        _log(f"Sieťová chyba: {e}")


# ── Formátovanie ──────────────────────────────────────────────

def _format_message(listing: dict, score: dict | None) -> str:
    lines = []

    # Hlavička — deal score ak existuje
    if score and score["pct_below"] >= 10:
        lines.append(f"🔥 *DEAL: {score['label']}*")
    else:
        lines.append("🏠 *Nový inzerát*")

    lines.append("")
    lines.append(f"*{listing['title']}*")

    # Cena
    price = listing.get("price", 0)
    if price:
        lines.append(f"💰 {price:,} €".replace(",", " "))
    else:
        lines.append("💰 Cena neuvedená")

    # Plocha
    area = listing.get("area_m2", 0)
    if area:
        lines.append(f"📐 {area} m²")

    # Deal Score detail
    if score:
        lines.append(
            f"📊 {score['price_per_m2']:,} €/m²"
            f" vs priemer {score['avg_per_m2']:,} €/m²"
        )

    # Lokalita
    loc = listing.get("locality", "")
    if loc:
        lines.append(f"📍 {loc}")

    # Zdroj
    lines.append(f"🔗 [{listing['source']}]({listing['url']})")

    return "\n".join(lines)


def _log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [telegram] {msg}")
