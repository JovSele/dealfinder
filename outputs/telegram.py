# outputs/telegram.py — Telegram alerting
#
# Rozhranie: send_alert(listing, score) → None
# Všetky output moduly musia implementovať toto rozhranie.
#
# Free kanál: send_free_alert(listing, score) → None
# Posiela s ⏰ badge a informáciou o oneskorení.

import requests
import time
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
        elif r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 30)
            _log(f"Rate limit — čakám {retry_after}s")
            time.sleep(retry_after + 1)
            # jeden retry
            r2 = requests.post(url, json=payload, timeout=10)
            if r2.status_code == 200:
                _log(f"Alert odoslaný po retry (chat {chat_id}): {text[:50]}")
            else:
                _log(f"Retry zlyhalo {r2.status_code}: {r2.text[:100]}")
        else:
            _log(f"Telegram API chyba {r.status_code} pre chat [{chat_id}]: {r.text[:100]}")
    except requests.RequestException as e:
        _log(f"Sieťová chyba: {e}")
    
    time.sleep(0.5)  # vždy čakaj medzi správami


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
            f" vs medián {_fmt_price(score['avg_per_m2'], currency)}/m²"
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

def send_admin(msg: str) -> None:
    """Pošli správu do admin kanála / chatu."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_ADMIN_CHAT_ID:
        return
    _send(config.TELEGRAM_ADMIN_CHAT_ID, msg)


def send_run_summary(stats: dict, free_sent: int, error: str | None = None) -> None:
    """Odošle admin súhrn po každom GitHub Actions behu."""
    from datetime import datetime
    ts = datetime.now().strftime("%d.%m. %H:%M")

    if error:
        msg = (
            f"🔴 *DealFinder — CHYBA* `{ts}`\n\n"
            f"```\n{error[:300]}\n```"
        )
    else:
        dealy = stats.get("deals", 0)
        deal_icon = "🔥" if dealy > 0 else "✅"
        msg = (
            f"{deal_icon} *DealFinder run* `{ts}`\n\n"
            f"📥 Stiahnuté: `{stats.get('scraped', 0)}`\n"
            f"🆕 Nové: `{stats.get('new', 0)}`\n"
            f"💎 Dealy: `{dealy}`\n"
            f"📨 Alerty: `{stats.get('alerted', 0)}`\n"
            f"⏰ Free odoslané: `{free_sent}`"
        )

    send_admin(msg)


def send_weekly_free_summary(deals_this_week: list) -> None:
    """Týždenný súhrn do FREE kanála — len ak boli nejaké dealy."""
    if not deals_this_week:
        return  # ticho je lepšie ako "tento týždeň nič"

    best = max(deals_this_week, key=lambda d: d.get("pct_below", 0))
    currency = _currency(best)

    msg = (
        f"📊 *Týždenný súhrn — DealFinder FREE*\n\n"
        f"Tento týždeň sme našli *{len(deals_this_week)} dealy*.\n\n"
        f"🏆 Najlepší deal:\n"
        f"*{best['title']}*\n"
        f"💰 {_fmt_price(best['price'], currency)} "
        f"(-{best.get('pct_below', 0):.0f}% pod trhom)\n"
        f"📍 {best.get('locality', '')}\n\n"
        f"_Chceš alerty okamžite? → dealfinder.sk_"
    )

    if config.TELEGRAM_TOKEN and config.TELEGRAM_FREE_CHAT_ID:
        _send(config.TELEGRAM_FREE_CHAT_ID, msg)
