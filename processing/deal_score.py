# processing/deal_score.py — výpočet Deal Score
#
# Deal Score = o koľko % je inzerát lacnejší ako MEDIÁN v lokalite (cena/m²)
# Príklad: med. 3000 €/m², inzerát 2500 €/m² → score = -16.7%
#
# Zmeny oproti v1:
#   - aritmetický priemer → medián (robustnejší voči outlierom)
#   - fallback na okres ak lokalita má < MIN_SAMPLES

import statistics

import config
from storage import db

# Ak lokalita má menej samples, rozšírime na okres (district)
DISTRICT_FALLBACK_THRESHOLD = 15


def score(listing: dict) -> dict | None:
    """Vypočítaj Deal Score pre inzerát.

    Vracia:
        dict so score ak je vypočítateľný, inak None.

        {
            "pct_below":    float,  # napr. 15.3 (znamená −15.3% pod trhom)
            "price_per_m2": int,    # cena inzerátu za m²
            "avg_per_m2":   int,    # medián lokality za m² (názov zachovaný pre kompatibilitu)
            "label":        str,    # napr. "−15% pod trhom"
            "sample_size":  int,    # počet inzerátov v mediáne
            "scope":        str,    # "locality" | "district" — čo bolo použité
        }
    """
    price    = listing.get("price", 0)
    area     = listing.get("area_m2", 0)
    locality = listing.get("locality", "")
    source   = listing.get("source")

    if price <= 0 or area <= 0:
        return None

    listing_per_m2 = price / area

    # 1. Skús lokalitu
    comparables, scope = _get_comparables(locality, listing.get("district", ""), source)

    if comparables is None:
        return None

    prices_per_m2 = [c["price"] / c["area_m2"] for c in comparables]
    median_per_m2 = statistics.median(prices_per_m2)

    if median_per_m2 <= 0:
        return None

    pct_below = (median_per_m2 - listing_per_m2) / median_per_m2 * 100

    return {
        "pct_below":    round(pct_below, 1),
        "price_per_m2": round(listing_per_m2),
        "avg_per_m2":   round(median_per_m2),   # zachované pre kompatibilitu s telegram.py
        "label":        _label(pct_below),
        "sample_size":  len(comparables),
        "scope":        scope,
    }


def is_deal(score_result: dict | None) -> bool:
    """True ak inzerát prekračuje threshold z configu."""
    if score_result is None:
        return False
    return score_result["pct_below"] >= config.DEAL_SCORE_THRESHOLD_PCT


def _get_comparables(locality: str, district: str, source: str) -> tuple[list | None, str]:
    """
    Vráť (comparables, scope) kde scope je "locality" alebo "district".
    Vráť (None, "") ak ani jeden nemá dosť dát.
    """
    # Primárne: lokalita
    comps = _fetch_valid(locality, source)
    if len(comps) >= config.DEAL_SCORE_MIN_SAMPLES:
        if len(comps) >= DISTRICT_FALLBACK_THRESHOLD:
            return comps, "locality"
        # Málo samples v lokalite — skús okres ako rozšírenie
        if district and district != locality:
            district_comps = _fetch_valid(district, source)
            if len(district_comps) >= config.DEAL_SCORE_MIN_SAMPLES:
                return district_comps, "district"
        return comps, "locality"

    # Fallback: okres
    if district and district != locality:
        district_comps = _fetch_valid(district, source)
        if len(district_comps) >= config.DEAL_SCORE_MIN_SAMPLES:
            return district_comps, "district"

    return None, ""


def _fetch_valid(locality: str, source: str) -> list:
    """Stiahni comparables a odfiltruj neplatné."""
    if not locality:
        return []
    comparables = db.get_listings_by_locality(locality, source)
    return [
        c for c in comparables
        if c.get("area_m2", 0) > 0 and c.get("price", 0) > 0
    ]


def _label(pct_below: float) -> str:
    if pct_below >= 20:
        return f"−{pct_below:.0f}% pod trhom  🔥"
    if pct_below >= 10:
        return f"−{pct_below:.0f}% pod trhom"
    if pct_below >= 0:
        return f"−{pct_below:.0f}% pod trhom"
    return f"+{abs(pct_below):.0f}% nad trhom"