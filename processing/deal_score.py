# processing/deal_score.py — výpočet Deal Score
#
# Deal Score = o koľko % je inzerát lacnejší ako priemer v lokalite (cena/m²)
# Príklad: priem. 3000 €/m², inzerát 2500 €/m² → score = -16.7%

import config
from storage import db


def score(listing: dict) -> dict | None:
    """Vypočítaj Deal Score pre inzerát.

    Vracia:
        dict so score ak je vypočítateľný, inak None.

        {
            "pct_below":   float,  # napr. 15.3 (znamená −15.3% pod trhom)
            "price_per_m2": int,   # cena inzerátu za m²
            "avg_per_m2":  int,    # priemer lokality za m²
            "label":       str,    # napr. "−15% pod trhom"
            "sample_size": int,    # počet inzerátov v priemere
        }
    """
    price   = listing.get("price", 0)
    area    = listing.get("area_m2", 0)
    locality = listing.get("locality", "")

    # Potrebujeme cenu aj plochu
    if price <= 0 or area <= 0:
        return None

    listing_per_m2 = price / area

    # Získaj porovnateľné inzeráty z DB
    comparables = db.get_listings_by_locality(locality, listing.get("source"))
    comparables = [
        c for c in comparables
        if c["area_m2"] > 0 and c["price"] > 0
    ]

    if len(comparables) < config.DEAL_SCORE_MIN_SAMPLES:
        return None

    avg_per_m2 = sum(c["price"] / c["area_m2"] for c in comparables) / len(comparables)

    if avg_per_m2 <= 0:
        return None

    pct_below = (avg_per_m2 - listing_per_m2) / avg_per_m2 * 100

    return {
        "pct_below":    round(pct_below, 1),
        "price_per_m2": round(listing_per_m2),
        "avg_per_m2":   round(avg_per_m2),
        "label":        _label(pct_below),
        "sample_size":  len(comparables),
    }


def is_deal(score_result: dict | None) -> bool:
    """True ak inzerát prekračuje threshold z configu."""
    if score_result is None:
        return False
    return score_result["pct_below"] >= config.DEAL_SCORE_THRESHOLD_PCT


def _label(pct_below: float) -> str:
    if pct_below >= 20:
        return f"−{pct_below:.0f}% pod trhom  🔥"
    if pct_below >= 10:
        return f"−{pct_below:.0f}% pod trhom"
    if pct_below >= 0:
        return f"−{pct_below:.0f}% pod trhom"
    return f"+{abs(pct_below):.0f}% nad trhom"
