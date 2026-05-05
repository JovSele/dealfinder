# processing/filters.py — filtrovanie a validácia inzerátov

import config
from storage import db

# ── Konfigurácia filtrov ──────────────────────────────────────

# Typy nehnuteľností ktoré VYLÚČIME z alertov (lowercase)
_EXCLUDED_PROPERTY_TYPES = [
    "chaty", "chata", "chalupy", "chalupa", "rekreační", "rekreačný",
    "záhradná", "záhradné", "záhradný", "zahradní",
    "stodola", "garáž", "garážové",
]

# Slová v title/description ktoré signalizujú junk listing
_EXCLUDED_KEYWORDS = [
    # Aukcie a dražby
    "dražba", "dražby", "dražební", "aukce", "aukcia", "exekuce", "exekúcia",
    "insolvence", "insolvenční", "nucený prodej",
    # Podiely
    "podíl", "podiel", "spoluvlastnický podíl", "id. 1/", "id.1/",
    # Junk typy
    "mobilheim", "maringotka", "tiny house", "tinyhouse",
    "záhradná chata", "záhradná chatka",
    # Rezervované / mŕtve
    "rezervováno", "rezervované", "prodáno", "predané",
]

# Deal Score cap — skóre nad týmto % je outlier (dražba, ruina, chyba parsingu)
DEAL_SCORE_MAX_PCT = config.DEAL_SCORE_MAX_PCT

# Max alertov na jeden run do plateného kanála
ALERT_LIMIT_PER_RUN = config.ALERT_LIMIT_PER_RUN


# ── Základné filtre ───────────────────────────────────────────

def is_valid(listing: dict) -> bool:
    """Základná validácia inzerátu pred uložením."""
    if not listing.get("id"):
        return False
    if not listing.get("url"):
        return False
    if not listing.get("title"):
        return False
    price = listing.get("price", 0)
    if price > 0 and price < config.FILTER_MIN_PRICE_EUR:
        return False
    return True


def is_new(listing: dict) -> bool:
    """True ak inzerát sme ešte nevideli (DB check)."""
    return db.is_new(listing["id"], listing["source"])


def is_relevant(listing: dict) -> bool:
    """Filtruje typy nehnuteľností ktoré nie sú investičné."""
    title = (listing.get("title") or "").lower()
    description = (listing.get("description") or "").lower()
    text = title + " " + description

    if any(excl in title for excl in _EXCLUDED_PROPERTY_TYPES):
        return False
    if any(kw in text for kw in _EXCLUDED_KEYWORDS):
        return False
    return True


def is_score_valid(score_result: dict | None) -> bool:
    """Vráti False ak je Deal Score podozrivo vysoký (outlier).

    -85% pod trhom takmer nikdy nie je reálny deal —
    je to dražba, ruina alebo chyba v parsingu plochy.
    """
    if score_result is None:
        return False
    return score_result["pct_below"] <= DEAL_SCORE_MAX_PCT


# ── Pipeline ──────────────────────────────────────────────────

def apply(listings: list[dict]) -> list[dict]:
    """Vyfiltruj zoznam inzerátov — vráť len platné a nové.

    Pipelina:
        1. is_valid()    — odmietni garbage
        2. is_new()      — odmietni duplicity
        3. is_relevant() — odmietni chaty/chalupy
    """
    valid = [l for l in listings if is_valid(l)]
    invalid = len(listings) - len(valid)
    if invalid:
        _log(f"Odmietnutých {invalid} neplatných inzerátov")

    new = [l for l in valid if is_new(l)]
    dupes = len(valid) - len(new)
    if dupes:
        _log(f"Preskočených {dupes} duplicít")

    relevant = [l for l in new if is_relevant(l)]
    irrelevant = len(new) - len(relevant)
    if irrelevant:
        _log(f"Vylúčených {irrelevant} nerelevantných typov (chaty/chalupy)")

    return relevant


def top_deals(scored_listings: list[tuple[dict, dict]], limit: int = ALERT_LIMIT_PER_RUN) -> list[tuple[dict, dict]]:
    """Z ohodnotených inzerátov vráť len top N — zoradené podľa Deal Score.

    Vstup:  [(listing, score_result), ...]  — len tie kde is_deal() == True
    Výstup: top `limit` zoradených od najlepšieho

    Použitie v runner.py:
        deals = [(l, sc) for l, sc in scored if deal_score.is_deal(sc) and is_score_valid(sc)]
        for listing, sc in filters.top_deals(deals):
            telegram.send_alert(listing, sc)
    """
    valid = [(l, sc) for l, sc in scored_listings if is_score_valid(sc)]
    sorted_deals = sorted(valid, key=lambda x: x[1]["pct_below"], reverse=True)
    if len(sorted_deals) > limit:
        _log(f"Alert limit: {len(sorted_deals)} dealov → posielam top {limit}")
    return sorted_deals[:limit]


# ── Logging ───────────────────────────────────────────────────

def _log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [filters] {msg}")
