#!/usr/bin/env python3
"""
generate_top_deal.py
Vytiahne top deal zo Sreality listings, spustí scoring a uloží do /var/www/vamuo/deal.json
Spúšťaj 1-2x denne cez cron.
"""

import sys
import os
import json
import statistics
from datetime import datetime, timedelta


# Pridaj /opt/dealfinder do path aby sme mohli importovať moduly
sys.path.insert(0, "/opt/dealfinder")

import requests
import config
from storage import db
from processing import deal_score

def is_listing_active(url: str) -> bool:
    try:
        r = requests.get(url, timeout=8, allow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200
    except:
        return False

OUTPUT_PATH = "/var/www/vamuo/deal.json"
MIN_COHORT  = 20          # Minimálny počet comparables pre verejný display
SOURCE      = "sreality"  # Len Sreality


def get_all_sreality_listings():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(
        "postgresql://dealfinder:dealfinder123@localhost:5432/dealfinder"
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, title, price, area_m2, locality, district, rooms,
               building_type, condition, has_elevator, has_balcony,
               has_parking, has_terrace, owner_direct, ownership_type,
               url, source, neighbourhood, first_seen
        FROM listings
        WHERE source LIKE %s
          AND price > 0
          AND area_m2 > 0
          AND status != 'removed'
          AND id IN (SELECT id FROM seen_ids)
          AND url NOT LIKE '%%/-/-/%%'
          AND first_seen >= NOW() - INTERVAL '3 days'
        ORDER BY first_seen DESC
        LIMIT 2000
     """, (f"%{SOURCE}%", ))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def score_all(listings):
    """Skóruj všetky listings, vráť len tie s dostatočnou confidence."""
    results = []
    for listing in listings:
        try:
            sc = deal_score.score(listing)
            if sc is None:
                continue
            if not deal_score.is_deal(sc):
                continue
            if sc["sample_size"] < MIN_COHORT:
                continue
            results.append((listing, sc))
        except Exception as e:
            continue
    return results

def fix_sreality_url(listing):
    """Ak URL má starý formát, vráť aspoň funkčný odkaz."""
    url = listing.get("url", "")
    # Starý formát: /detail/prodej/byty/-/-/ID
    # Nový formát: /detail/prodej/byt/3+kk/brno-.../ID
    # Ak obsahuje '/-/-/', skúsime vybudovať lepší link
    if "/-/-/" in url:
        # Aspoň oprav byty -> byt
        url = url.replace("/byty/", "/byt/").replace("/domy/", "/dum/")
    return url

def build_deal_json(listing, sc):
    """Zostav JSON pre frontend."""
    tags_good = []
    tags_warn = []

    bt = listing.get("building_type", "")
    if bt == "brick":
        tags_good.append("Cihla")
    elif bt == "panel":
        tags_warn.append("Panelák")

    if listing.get("has_balcony"):
        tags_good.append("Balkón")
    if listing.get("has_parking"):
        tags_good.append("Parkování")
    if listing.get("has_terrace"):
        tags_good.append("Terasa")
    if listing.get("owner_direct"):
        tags_good.append("Přímý prodej")

    cond = listing.get("condition", "")
    if cond == "new_build":
        tags_good.append("Novostavba")
    elif cond == "after_reconstruction":
        tags_good.append("Po rekonstrukci")
    elif cond == "original":
        tags_warn.append("Původní stav")

    if not listing.get("has_elevator"):
        tags_warn.append("Bez výtahu")

    ow = listing.get("ownership_type", "")
    if ow == "cooperative":
        tags_warn.append("Družstevní")

    # Confidence tier
    sample_size = sc["sample_size"]
    if sample_size >= 30:
        confidence = "high"
        conf_label = f"{sample_size} srovnání · vysoká shoda"
    elif sample_size >= 20:
        confidence = "medium"
        conf_label = f"{sample_size} srovnání · střední shoda"
    else:
        confidence = "low"
        conf_label = f"{sample_size} srovnání · nízká shoda"

    pct = sc["pct_below"]
    savings = round((sc["median_per_m2"] - sc["price_per_m2"]) * listing["area_m2"])

    # Delay — zobraz čas zachytenia mínus 6 hodín (delay simulácia)
    captured_at = datetime.now() - timedelta(hours=6)

    return {
        "id":             listing["id"],
        "title":          listing["title"],
        "price":          listing["price"],
        "area_m2":        listing["area_m2"],
        "rooms":          listing.get("rooms", ""),
        "locality":       listing.get("locality", ""),
        "district":       listing.get("district", ""),
        "url":            fix_sreality_url(listing),
        "pct_below":      pct,
        "price_per_m2":   sc["price_per_m2"],
        "median_per_m2":  sc["median_per_m2"],
        "sample_size":    sample_size,
        "confidence":     confidence,
        "conf_label":     conf_label,
        "savings":        savings,
        "tags_good":      tags_good,
        "tags_warn":      tags_warn,
        "captured_at":    captured_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "generated_at":   datetime.now().isoformat(),
    }


def main():
    print(f"[{datetime.now()}] Načítavam listings...")
    listings = get_all_sreality_listings()
    print(f"  → {len(listings)} listings načítaných")

    print("Skórujem...")
    scored = score_all(listings)
    print(f"  → {len(scored)} dealov prešlo filter")

    if not scored:
        print("Žiadne dealy — neprepisujem deal.json")
        return

    # Zoraď podľa pct_below DESC, vezmi top 1
    scored.sort(key=lambda x: x[1]["pct_below"], reverse=True)
    best_listing, best_sc = None, None
    for listing, sc in scored[:10]:
        print(f"  Overujem: {listing['url'][:60]}...")
        if is_listing_active(listing["url"]):
            best_listing, best_sc = listing, sc
            break
        else:
            print(f"  → Neaktívny, skipping")

    if best_listing is None:
        print("Žiadny aktívny deal — neprepisujem deal.json")
        return

    print(f"  → Najlepší deal: {best_sc['pct_below']}% pod mediánom, {best_sc['sample_size']} comparables")
    print(f"     {best_listing['title']}")

    deal = build_deal_json(best_listing, best_sc)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(deal, f, ensure_ascii=False, indent=2)

    print(f"  → Uložené do {OUTPUT_PATH}")


if __name__ == "__main__":
    main()