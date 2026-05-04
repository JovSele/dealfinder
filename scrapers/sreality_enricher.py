# scrapers/sreality_enricher.py
"""
Obohacuje listingy o dáta z detail endpointu Sreality.
Volá sa po každom scrape cykle pre unenriched listingy.
"""
import time
import re
import requests
from storage import db

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sreality.cz/",
    "Accept": "application/json",
}

DETAIL_URL = "https://www.sreality.cz/api/cs/v2/estates/{hash_id}"

# Mapovanie slovenských/českých názvov na naše stĺpce
_CONDITION_MAP = {
    "velmi dobrý":        "very_good",
    "dobrý":              "good",
    "před rekonstrukcí":  "before_reconstruction",
    "po rekonstrukci":    "after_reconstruction",
    "novostavba":         "new_building",
    "ve výstavbě":        "under_construction",
    "projekt":            "project",
    "původní stav":       "original",
}

_BUILDING_MAP = {
    "cihlová":   "brick",
    "panelová":  "panel",
    "skeletová": "skeleton",
    "dřevostavba": "wood",
    "nízkoenergetická": "low_energy",
    "pasivní":   "passive",
    "ostatní":   "other",
}

_OWNERSHIP_MAP = {
    "osobní":      "personal",
    "družstevní":  "cooperative",
    "státní/obecní": "state",
    "ostatní":     "other",
}

_ENERGY_MAP = {
    "a": "A", "b": "B", "c": "C",
    "d": "D", "e": "E", "f": "F", "g": "G",
}


def enrich_batch(limit: int = 30) -> int:
    """Obohaťi dávku unenriched listingov. Vráti počet úspešných."""
    pending = db.get_unenriched(limit=limit)
    success = 0

    for row in pending:
        listing_id = row["id"]           # napr. "sreality_1234567"
        hash_id    = listing_id.replace("sreality_", "")

        try:
            data = _fetch_detail(hash_id)
            if data:
                db.update_enrichment(listing_id, row["source"], data)
                success += 1
        except Exception as e:
            print(f"[enricher] Chyba pre {hash_id}: {e}")

        time.sleep(1.5)   # buď slušný k Sreality

    return success


def _fetch_detail(hash_id: str) -> dict | None:
    try:
        url = DETAIL_URL.format(hash_id=hash_id)
        r   = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return _parse_detail(data)
    except Exception:
        return None


def _parse_detail(data: dict) -> dict:
    items = {
        item.get("name", "").lower(): item.get("value", "")
        for item in data.get("items", [])
    }

    # --- Podlažie ---
    floor, floor_total = _parse_floor(items.get("podlaží", ""))

    # --- Boolean featury ---
    has_elevator = _has_item(items, ["výtah"])
    has_balcony  = _has_item(items, ["balkón", "balkón / terasa"])
    has_parking  = _has_item(items, ["parkování", "garáž", "garážové stání"])
    has_terrace  = _has_item(items, ["terasa"])

    # --- Stav ---
    condition_raw = items.get("stav objektu", items.get("stav", ""))
    condition = _CONDITION_MAP.get(condition_raw.lower(), condition_raw.lower() or None)

    # --- Typ budovy ---
    building_raw = items.get("typ budovy", items.get("konstrukce budovy", ""))
    building_type = _BUILDING_MAP.get(building_raw.lower(), building_raw.lower() or None)

    # --- Energetická trieda ---
    energy_raw = items.get("energetická náročnost", "")
    energy_class = _ENERGY_MAP.get(energy_raw.strip().lower(), energy_raw.upper() or None)

    # --- Vlastníctvo ---
    ownership_raw = items.get("vlastnictví", "")
    ownership_type = _OWNERSHIP_MAP.get(ownership_raw.lower(), ownership_raw.lower() or None)

    return {
        "floor":          floor,
        "floor_total":    floor_total,
        "has_elevator":   has_elevator,
        "has_balcony":    has_balcony,
        "has_parking":    has_parking,
        "has_terrace":    has_terrace,
        "condition":      condition,
        "building_type":  building_type,
        "energy_class":   energy_class,
        "ownership_type": ownership_type,
    }


def _parse_floor(value: str):
    """
    '3. podlaží z 8' → (3, 8)
    'přízemí'        → (0, None)
    ''               → (None, None)
    """
    if not value:
        return None, None
    if "přízemí" in value.lower():
        return 0, None
    m = re.search(r"(\d+)\.\s*podlaží\s+z\s+(\d+)", value)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)", value)
    if m:
        return int(m.group(1)), None
    return None, None


def _has_item(items: dict, keys: list[str]) -> bool | None:
    """True ak sa niektorý kľúč nachádza v items a má neprázdnu hodnotu."""
    for key in keys:
        if key in items and items[key]:
            return True
    return None   # None = nevieme (nechceme zapisovať False ak kľúč chýba)
