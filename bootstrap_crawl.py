"""
Bootstrap crawl — stiahne celé Sreality do Postgres.
Spusti raz cez noc. Ignoruje "known → stop" logiku.
"""

import re
import time
import requests
import sys
import os

sys.path.insert(0, '/app')
os.chdir('/app')

from storage import db

BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sreality.cz/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "cs-CZ,cs;q=0.9",
}

# Všetky regióny CZ
CONFIGS = [
    {"source": "sreality/byty/stredocesky",  "cat_main": 1, "region": 11},
    {"source": "sreality/domy/stredocesky",  "cat_main": 2, "region": 11},
    {"source": "sreality/byty/praha",        "cat_main": 1, "region": 10},
    {"source": "sreality/domy/praha",        "cat_main": 2, "region": 10},
    {"source": "sreality/byty/brno",         "cat_main": 1, "region": 64},
    {"source": "sreality/domy/brno",         "cat_main": 2, "region": 64},
    {"source": "sreality/byty/plzen",        "cat_main": 1, "region": 32},
    {"source": "sreality/domy/plzen",        "cat_main": 2, "region": 32},
    {"source": "sreality/byty/olomouc",      "cat_main": 1, "region": 71},
    {"source": "sreality/domy/olomouc",      "cat_main": 2, "region": 71},
    {"source": "sreality/byty/ostrava",      "cat_main": 1, "region": 80},
    {"source": "sreality/domy/ostrava",      "cat_main": 2, "region": 80},
    {"source": "sreality/byty/liberec",      "cat_main": 1, "region": 51},
    {"source": "sreality/byty/hradec",       "cat_main": 1, "region": 52},
    {"source": "sreality/byty/pardubice",    "cat_main": 1, "region": 53},
    {"source": "sreality/byty/vysocina",     "cat_main": 1, "region": 63},
    {"source": "sreality/byty/zlinsky",      "cat_main": 1, "region": 72},
    {"source": "sreality/byty/karlovarsky",  "cat_main": 1, "region": 41},
    {"source": "sreality/byty/ustecky",      "cat_main": 1, "region": 42},
    {"source": "sreality/byty/jihocesky",    "cat_main": 1, "region": 31},
]

session = requests.Session()
session.headers.update(HEADERS)


def parse_area(title):
    m = re.search(r"(\d+)\s*m²", title)
    return int(m.group(1)) if m else 0


def normalize_locality(locality):
    if not locality:
        return ""
    parts = locality.split(",")
    city = parts[-1].strip() if len(parts) >= 2 else locality.strip()
    city = re.sub(r"^okres\s+", "", city, flags=re.IGNORECASE)
    if " - " in city:
        city = city.split(" - ")[0].strip()
    return city.strip()


def parse_rooms(title):
    m = re.search(r"(\d+\+(?:kk|\d))", title, re.IGNORECASE)
    if m:
        return m.group(1)
    if re.search(r"garson", title, re.IGNORECASE):
        return "1+kk"
    return ""


def fetch_page(cfg, page):
    params = {
        "category_main_cb": cfg["cat_main"],
        "category_type_cb": 1,  # vždy predaj
        "locality_region_id": cfg["region"],
        "per_page": 20,
        "page": page,
    }
    try:
        r = session.get(BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("_embedded", {}).get("estates", [])
    except Exception as e:
        print(f"  [!] Chyba strana {page}: {e}")
        time.sleep(5)
        return []


def crawl_source(cfg):
    source = cfg["source"]
    total_new = 0
    total_seen = 0
    empty_streak = 0

    print(f"\n{'='*55}")
    print(f"  {source}")
    print(f"{'='*55}")

    for page in range(1, 501):
        estates = fetch_page(cfg, page)

        if not estates:
            empty_streak += 1
            if empty_streak >= 3:
                print(f"  [→] Strana {page}: 3x prázdna → koniec")
                break
            time.sleep(3)
            continue

        empty_streak = 0
        new_on_page = 0

        for estate in estates:
            hash_id = str(estate.get("hash_id", ""))
            if not hash_id:
                continue

            title    = estate.get("name", "").strip()
            price    = int(estate.get("price", 0))
            locality = estate.get("locality", "").strip()
            area_m2  = parse_area(title)
            city     = normalize_locality(locality)
            rooms    = parse_rooms(title)
            cat_slug = "byty" if cfg["cat_main"] == 1 else "domy"

            url = f"https://www.sreality.cz/detail/prodej/{cat_slug}/-/-/{hash_id}"

            listing = {
                "id": f"sreality_{hash_id}",
                "source": source,
                "title": title,
                "url": url,
                "price": price,
                "area_m2": area_m2,
                "locality": city,
                "district": locality,
                "rooms": rooms,
            }

            if db.is_new(listing["id"], listing["source"]):
                db.save_listing(listing)
                new_on_page += 1
                total_new += 1
            else:
                total_seen += 1

        print(f"  Strana {page:3d} | nových: {new_on_page:3d} | celkom: {total_new:5d}")
        time.sleep(1.3)

    print(f"  → HOTOVO: {total_new} nových, {total_seen} existujúcich")
    return total_new


# ── MAIN ──────────────────────────────────────────────────────

print("\n" + "="*55)
print("  DEALFINDER BOOTSTRAP CRAWL — celá CZ")
print("="*55)

grand_total = 0
for cfg in CONFIGS:
    grand_total += crawl_source(cfg)

print(f"\n{'='*55}")
print(f"  BOOTSTRAP DOKONČENÝ — celkovo nových: {grand_total}")
print(f"{'='*55}\n")