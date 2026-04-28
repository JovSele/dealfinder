"""
scrapers/sreality.py
====================
Sreality.cz scraper — integrovaný do modulárnej architektúry DealFinder.

Podporuje:
  - category_main_cb=1  → byty
  - category_main_cb=2  → domy

Ceny sú v CZK (natívne zo Sreality API).
Deal Score v db.py pracuje s price/area — funguje rovnako pre CZK aj EUR,
pokiaľ je celá lokalita v rovnakej mene.

Použitie v runner.py:
    from scrapers.sreality import SrealityScraper
    SCRAPERS = [
        BazosScraper(...),
        SrealityScraper(category="byty",  region_id=16),  # Stredočeský kraj
        SrealityScraper(category="domy",  region_id=16),
    ]
"""

import time
import hashlib
import requests
from scrapers.base import BaseScraper

# ─────────────────────────────────────────
# KONŠTANTY
# ─────────────────────────────────────────

BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sreality.cz/",
    "Accept":  "application/json, text/plain, */*",
    "Accept-Language": "cs-CZ,cs;q=0.9",
}

# category_main_cb hodnoty
CATEGORY_BYTY = 1
CATEGORY_DOMY = 2

# category_type_cb
TYPE_PREDAJ = 1

# Regióny (locality_region_id)
REGIONS = {
    "praha":            10,
    "stredocesky_kraj": 11,
    "jihocesky_kraj":   17,
    "plzensky_kraj":    18,
    "karlovarsky_kraj": 19,
    "ustecky_kraj":     20,
    "liberecky_kraj":   21,
    "kralovehradecky":  22,
    "pardubicky_kraj":  23,
    "vysocina":         24,
    "jihomoravsky":     25,
    "olomoucky_kraj":   26,
    "zlinsky_kraj":     27,
    "moravskoslezsky":  28,
}

RETRY_ATTEMPTS = 3
RETRY_DELAY_SEC = 5
PER_PAGE = 20


# ─────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────

class SrealityScraper(BaseScraper):
    """
    Scraper pre Sreality.cz API.

    Parametre:
        category  : "byty" | "domy"
        region_id : int — ID regiónu (napr. 16 = Stredočeský kraj)
        pages     : int — koľko strán stiahnuť (default 5, každá = 20 listingov)
    """

    def __init__(self, category: str = "byty", region_id: int = 16, pages: int = 5):
        if category not in ("byty", "domy"):
            raise ValueError(f"category musí byť 'byty' alebo 'domy', nie '{category}'")

        self.category     = category
        self.region_id    = region_id
        self.pages        = pages
        self.category_cb  = CATEGORY_BYTY if category == "byty" else CATEGORY_DOMY
        self.source       = f"sreality_{category}"   # identifikátor zdroja v DB

    # ── public ────────────────────────────

    def fetch(self) -> list[dict]:
        """
        Stiahni všetky stránky a vráť zoznam štandardizovaných listingov.
        Kompatibilné s BaseScraper kontraktom.
        """
        self._log(
            f"Sreality [{self.category} | región {self.region_id}] "
            f"— sťahujem {self.pages} strán..."
        )
        results = []

        for page in range(1, self.pages + 1):
            raw = self._fetch_page(page)
            if raw is None:
                self._log(f"  Strana {page}: chyba — prerušujem")
                break
            if not raw:
                self._log(f"  Strana {page}: prázdna — koniec")
                break

            parsed = [self._parse(item) for item in raw]
            parsed = [p for p in parsed if p]           # odfiltruj None
            results.extend(parsed)
            self._log(f"  Strana {page}: +{len(parsed)} (celkom {len(results)})")
            time.sleep(0.8)

        self._log(f"✅ Sreality [{self.category}]: {len(results)} listingov\n")
        return results

    # ── private ───────────────────────────

    def _fetch_page(self, page: int) -> list | None:
        """Stiahni jednu stránku. Vráť list surových itemov alebo None pri chybe."""
        params = {
            "category_main_cb":   self.category_cb,
            "category_type_cb":   TYPE_PREDAJ,
            "locality_region_id": self.region_id,
            "per_page":           PER_PAGE,
            "page":               page,
        }

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                r = requests.get(
                    BASE_URL,
                    headers=HEADERS,
                    params=params,
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                return data.get("_embedded", {}).get("estates", [])

            except requests.exceptions.HTTPError as e:
                self._log(f"  HTTP chyba (pokus {attempt}/{RETRY_ATTEMPTS}): {e}")
            except requests.exceptions.RequestException as e:
                self._log(f"  Sieťová chyba (pokus {attempt}/{RETRY_ATTEMPTS}): {e}")
            except Exception as e:
                self._log(f"  Neočakávaná chyba (pokus {attempt}/{RETRY_ATTEMPTS}): {e}")

            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC)

        return None

    def _parse(self, raw: dict) -> dict | None:
        """
        Preveď surový Sreality item na štandardizovaný listing dict.
        Kompatibilný s _make_listing() z BaseScraper + db.save_listing().
        """
        try:
            hash_id = str(raw.get("hash_id", ""))
            if not hash_id:
                return None

            name     = raw.get("name", "").strip()
            locality = raw.get("locality", "").strip()

            # Cena v CZK
            price_czk = raw.get("price_czk", {})
            price = price_czk.get("value_raw", 0) if isinstance(price_czk, dict) else 0

            # Alternatívne umiestnenie ceny
            if not price:
                price = raw.get("price", 0)

            # Plocha z meta_description napr. "3+1, 94 m²" alebo "Rodinný dům 120 m²"
            meta  = raw.get("meta_description", "")
            area  = self._extract_area(meta)

            # URL
            seo   = raw.get("seo", {})
            slug  = seo.get("locality", "")
            url   = (
                f"https://www.sreality.cz/detail/"
                f"{'prodej'}/{self.category}/{slug}/{hash_id}"
                if slug
                else f"https://www.sreality.cz/detail/{hash_id}"
            )

            # Izby / dispozícia z názvu
            rooms = self._extract_rooms(name)

            # Unikátne ID pre DB (source-prefixed)
            uid = f"sreality_{hash_id}"

            # content_hash pre _make_listing kompatibilitu
            content = f"{hash_id}{price}{locality}"
            content_hash = hashlib.md5(content.encode()).hexdigest()

            return {
                "id":           uid,
                "hash_id":      hash_id,          # pôvodné Sreality ID
                "title":        name,
                "price":        price,             # CZK
                "area_m2":      area,
                "price_per_m2": round(price / area) if area else 0,
                "locality":     locality,
                "district":     self._extract_district(locality),
                "rooms":        rooms,
                "url":          url,
                "source":       self.source,       # "sreality_byty" | "sreality_domy"
                "content_hash": content_hash,
            }

        except Exception as e:
            self._log(f"  _parse chyba pre item {raw.get('hash_id')}: {e}")
            return None

    # ── helpers ───────────────────────────

    @staticmethod
    def _extract_area(meta: str) -> float:
        """Vytiahni m² z textu."""
        import re
        match = re.search(r"(\d+[\.,]?\d*)\s*m[²2]", meta)
        if match:
            return float(match.group(1).replace(",", "."))
        return 0.0

    @staticmethod
    def _extract_rooms(name: str) -> str:
        """Vytiahni dispozíciu z názvu napr. '3+1', '2+kk', 'garsonka'."""
        import re
        match = re.search(r"\d\+(?:kk|\d)", name, re.IGNORECASE)
        if match:
            return match.group(0)
        if "garsonka" in name.lower() or "garsoniéra" in name.lower():
            return "1+kk"
        return ""

    @staticmethod
    def _extract_district(locality: str) -> str:
        """
        Vytiahni okres/mestskú časť z locality stringu.
        Sreality zvyčajne vracia napr. 'Praha 8' alebo 'Říčany u Prahy'.
        """
        if not locality:
            return ""
        # Ak obsahuje čiarku, vezmi poslednú časť (bývajúci okres)
        parts = [p.strip() for p in locality.split(",")]
        return parts[-1] if len(parts) > 1 else locality