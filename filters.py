# processing/filters.py — filtrovanie a validácia inzerátov

import config
from storage import db


def is_valid(listing: dict) -> bool:
    """Základná validácia inzerátu pred uložením."""
    if not listing.get("id"):
        return False
    if not listing.get("url"):
        return False
    if not listing.get("title"):
        return False
    # Odmietni inzeráty s príliš nízkou cenou (chyba parsingu alebo spam)
    price = listing.get("price", 0)
    if price > 0 and price < config.FILTER_MIN_PRICE_EUR:
        return False
    return True


def is_new(listing: dict) -> bool:
    """True ak inzerát sme ešte nevideli (DB check)."""
    return db.is_new(listing["id"], listing["source"])


def apply(listings: list[dict]) -> list[dict]:
    """Vyfiltruj zoznam inzerátov — vráť len platné a nové.

    Pipelina:
        1. is_valid()  — odmietni garbage
        2. is_new()    — odmietni duplicity
    """
    valid   = [l for l in listings if is_valid(l)]
    invalid = len(listings) - len(valid)
    if invalid:
        _log(f"Odmietnutých {invalid} neplatných inzerátov")

    new = [l for l in valid if is_new(l)]
    dupes = len(valid) - len(new)
    if dupes:
        _log(f"Preskočených {dupes} duplicít")

    return new


def _log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [filters] {msg}")
