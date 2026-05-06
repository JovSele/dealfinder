# processing/deal_score.py — výpočet Deal Score
#
# Deal Score = o koľko % je inzerát lacnejší ako MEDIÁN v lokalite (cena/m²)
# Príklad: med. 3000 €/m², inzerát 2500 €/m² → score = -16.7%
#
# Zmeny:
#   - aritmetický priemer → medián (robustnejší voči outlierom)
#   - fallback na okres ak lokalita má < MIN_SAMPLES
#   - category filter — byty sa porovnávajú len s bytmi, domy s domami
#   - price range filter — vylúči novostavky pri porovnaní so starými bytmi (±60% od ceny inzerátu)

import statistics

import config
from storage import db

# Ak lokalita má menej samples, rozšírime na okres (district)
DISTRICT_FALLBACK_THRESHOLD = 15

# Porovnávaj len comparables v tomto rozsahu od ceny inzerátu (napr. 0.4 = ±60%)
PRICE_RANGE_RATIO = 0.6


def score(listing: dict) -> dict | None:
    price    = listing.get("price", 0)
    area     = listing.get("area_m2", 0)
    locality = listing.get("locality", "")
    source   = listing.get("source")

    if price <= 0 or area <= 0:
        return None

    listing_per_m2 = price / area
    category = _category(listing)

    comparables, scope, cohort_quality = _get_comparables(
        locality, listing.get("district", ""), source, category, listing_per_m2, listing
    )

    if comparables is None:
        return None

    prices_per_m2 = [c["price"] / c["area_m2"] for c in comparables]
    median_per_m2 = statistics.median(prices_per_m2)

    if median_per_m2 <= 0:
        return None

    pct_below = (median_per_m2 - listing_per_m2) / median_per_m2 * 100

    return {
        "pct_below":      round(pct_below, 1),
        "price_per_m2":   round(listing_per_m2),
        "median_per_m2":  round(median_per_m2),
        "label":          _label(pct_below),
        "sample_size":    len(comparables),
        "scope":          scope,
        "cohort_quality": round(cohort_quality, 2),
    }


def is_deal(score_result: dict | None) -> bool:
    """True ak inzerát prekračuje threshold z configu."""
    if score_result is None:
        return False
    return score_result["pct_below"] >= config.DEAL_SCORE_THRESHOLD_PCT


def _get_comparables(locality, district, source, category="", listing_per_m2=0, listing=None):
    comps, quality = _fetch_valid(locality, source, category, listing_per_m2, listing)
    if len(comps) >= config.DEAL_SCORE_MIN_SAMPLES:
        if len(comps) >= DISTRICT_FALLBACK_THRESHOLD:
            return comps, "locality", quality
        if district and district != locality:
            district_comps, district_quality = _fetch_valid(district, source, category, listing_per_m2, listing)
            if len(district_comps) >= config.DEAL_SCORE_MIN_SAMPLES:
                return district_comps, "district", district_quality
        return comps, "locality", quality

    if district and district != locality:
        district_comps, district_quality = _fetch_valid(district, source, category, listing_per_m2, listing)
        if len(district_comps) >= config.DEAL_SCORE_MIN_SAMPLES:
            return district_comps, "district", district_quality

    return None, "", 0.0


def _rooms_bucket(rooms: str) -> str:
    """Zoskup dispozície do bucketov pre porovnanie."""
    if not rooms:
        return ""
    r = rooms.lower().replace(" ", "")
    if r in ("1+kk", "1+1"):
        return "1"
    if r in ("2+kk", "2+1"):
        return "2"
    if r in ("3+kk", "3+1"):
        return "3"
    if r in ("4+kk", "4+1", "5+kk", "5+1"):
        return "4+"
    return ""


def _fetch_valid(locality: str, source: str, category: str = "", listing_per_m2: float = 0, listing: dict = None) -> tuple[list, float]:
    if not locality:
        return [], 0.0

    comparables = db.get_listings_by_locality(locality, source)

    result = [
        c for c in comparables
        if c.get("area_m2", 0) > 0 and c.get("price", 0) > 0
    ]
    result = [c for c in result if _is_clean_comparable(c)]

    if category:
        result = [c for c in result if _category(c) == category]

    # Sleduj čo prešlo na exact match — základ quality score
    quality_points = 0.0
    quality_max    = 0.0

    # Condition filter
    if listing and listing.get("condition"):
        quality_max += 0.35
        listing_condition = listing["condition"]
        result_condition = [c for c in result if c.get("condition") == listing_condition]

        if listing_condition == "new_build":
            if len(result_condition) >= config.DEAL_SCORE_MIN_SAMPLES:
                result = result_condition
                quality_points += 0.35  # exact match
        else:
            result_no_new = [c for c in result if c.get("condition") != "new_build"]
            result_exact  = [c for c in result_no_new if c.get("condition") == listing_condition]
            if len(result_exact) >= config.DEAL_SCORE_MIN_SAMPLES:
                result = result_exact
                quality_points += 0.35  # exact match
            elif len(result_no_new) >= config.DEAL_SCORE_MIN_SAMPLES:
                result = result_no_new
                quality_points += 0.15  # partial — aspoň nie new_build

    # Rooms filter
    if listing and listing.get("rooms"):
        quality_max += 0.25
        rooms_bucket = _rooms_bucket(listing["rooms"])
        result_rooms = [c for c in result if _rooms_bucket(c.get("rooms", "")) == rooms_bucket]
        if len(result_rooms) >= config.DEAL_SCORE_MIN_SAMPLES:
            result = result_rooms
            quality_points += 0.25

    # Area filter
    if listing and listing.get("area_m2", 0) > 0:
        quality_max += 0.20
        area = listing["area_m2"]
        result_area = [
            c for c in result
            if abs(c.get("area_m2", 0) - area) <= max(20, area * 0.4)
        ]
        if len(result_area) >= config.DEAL_SCORE_MIN_SAMPLES:
            result = result_area
            quality_points += 0.20

    # Building type filter
    if listing and listing.get("building_type"):
        quality_max += 0.20
        bt = listing["building_type"]
        result_bt = [c for c in result if c.get("building_type") == bt]
        if len(result_bt) >= config.DEAL_SCORE_MIN_SAMPLES:
            result = result_bt
            quality_points += 0.20

    # Price range filter (vždy)
    if listing_per_m2 > 0:
        result = [
            c for c in result
            if PRICE_RANGE_RATIO <= (c["price"] / c["area_m2"]) / listing_per_m2 <= (1 / PRICE_RANGE_RATIO)
        ]

    quality = quality_points / quality_max if quality_max > 0 else 0.0
    return result, quality


def _is_clean_comparable(listing: dict) -> bool:
    """Vylúč junk zo súboru comparables — rovnaká logika ako filters.is_relevant()."""
    from processing.filters import _EXCLUDED_KEYWORDS, _EXCLUDED_PROPERTY_TYPES
    title = (listing.get("title") or "").lower()
    description = (listing.get("description") or "").lower()
    text = title + " " + description
    if any(excl in title for excl in _EXCLUDED_PROPERTY_TYPES):
        return False
    if any(kw in text for kw in _EXCLUDED_KEYWORDS):
        return False
    return True


def _category(listing: dict) -> str:
    """Urči kategóriu nehnuteľnosti pre správne porovnanie."""
    source = listing.get("source", "")
    title  = listing.get("title", "").lower()

    if "byty" in source:
        return "byt"
    if "domy" in source:
        if any(w in title for w in ["chata", "chalupa", "rekreační"]):
            return "chata"
        return "dum"

    if any(w in title for w in ["chata", "chalupa", "rekreační"]):
        return "chata"
    if any(w in title for w in ["rodinný", "rodinného", "dom", "dům"]):
        return "dum"
    return "byt"


def _label(pct_below: float) -> str:
    if pct_below >= 20:
        return f"−{pct_below:.0f}% pod trhom  🔥"
    if pct_below >= 10:
        return f"−{pct_below:.0f}% pod trhom"
    if pct_below >= 0:
        return f"−{pct_below:.0f}% pod trhom"
    return f"+{abs(pct_below):.0f}% nad trhom"
