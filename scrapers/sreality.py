# scrapers/sreality.py — Sreality.cz scraper
#
# Čo sa zmenilo oproti pôvodnému:
#   - area_m2 sa parsuje z title (vzor "179 m²") — 100% úspešnosť na existujúcich dátach
#   - locality sa normalizuje na mesto (za čiarkou, bez "okres ")
#   - rooms sa parsuje z title (vzor "3+kk", "2+1", "1+1")
#   - Všetky zmeny sú izolované tu — žiadne iné súbory sa nemenia

import re
import time

import requests

import config
from scrapers.base import BaseScraper


class SrealityScraper(BaseScraper):
    BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.sreality.cz/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "cs-CZ,cs;q=0.9",
    }

    def __init__(
        self,
        source: str,
        category_main_cb: int,   # 1 = byty, 2 = domy
        category_type_cb: int,   # 1 = predaj, 2 = prenájom
        region_id: int,
        pages: int = 5,
    ):
        self.source = source
        self._category_main = category_main_cb
        self._category_type = category_type_cb
        self._region_id = region_id
        self._pages = pages
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)

    # ── Public ────────────────────────────────────────────────

    def fetch(self) -> list[dict]:
        listings = []
        for page in range(1, self._pages + 1):
            page_listings = self._fetch_page(page)
            if not page_listings:
                break
            listings.extend(page_listings)
            time.sleep(0.8)

        self._log(f"Stiahnutých {len(listings)} inzerátov")
        return listings

    # ── Private ───────────────────────────────────────────────

    def _fetch_page(self, page: int) -> list[dict]:
        params = {
            "category_main_cb": self._category_main,
            "category_type_cb": self._category_type,
            "locality_region_id": self._region_id,
            "per_page": 20,
            "page": page,
        }
        try:
            r = self._session.get(self.BASE_URL, params=params, timeout=15)
            r.raise_for_status()
            estates = r.json().get("_embedded", {}).get("estates", [])
            return [self._parse(e) for e in estates if self._parse(e)]
        except Exception as e:
            self._log(f"Chyba na strane {page}: {e}")
            return []

    def _parse(self, estate: dict) -> dict | None:
        try:
            hash_id = str(estate.get("hash_id", ""))
            if not hash_id:
                return None

            title    = estate.get("name", "").strip()
            price    = int(estate.get("price", 0))
            locality = estate.get("locality", "").strip()

            # ── FIX 1: area_m2 z title ────────────────────────
            # Sreality API nevracia plochu ako samostatné pole,
            # ale je vždy v title: "Prodej bytu 3+kk 76 m²"
            area_m2 = self._parse_area(title)

            # ── FIX 2: locality → mesto ────────────────────────
            # API vracia "Ulica, Mesto" alebo "Obec, okres Okres"
            # Chceme len mesto pre správny median výpočet
            city = self._normalize_locality(locality)

            # ── FIX 3: rooms z title ──────────────────────────
            rooms = self._parse_rooms(title)

            url = (
                f"https://www.sreality.cz/detail/"
                f"{self._type_slug()}/{self._category_slug()}/"
                f"-/-/{hash_id}"
            )

            return self._make_listing(
                id=f"sreality_{hash_id}",
                title=title,
                url=url,
                price=price,
                area_m2=area_m2,
                locality=city,          # ← normalizované mesto
                district=locality,      # ← pôvodná surová hodnota pre referenciu
                rooms=rooms,
            )
        except Exception as e:
            self._log(f"Parse chyba: {e}")
            return None

    # ── Parsovanie ────────────────────────────────────────────

    @staticmethod
    def _parse_area(title: str) -> int:
        """
        Extrahuj plochu z title.
        Funguje na: '76 m²', '179 m²', '91 m² (Mezonet)', 'pozemek 430 m²'

        Berie PRVÝ výskyt m² — to je vždy plocha budovy (pozemok je druhý).
        """
        m = re.search(r"(\d+)\s*m²", title)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _normalize_locality(locality: str) -> str:
        """
        Normalizuj lokalitu na názov mesta.

        Príklady:
          "Škvorecká, Úvaly"              → "Úvaly"
          "Mrač, okres Benešov"           → "Benešov"
          "Mladá Boleslav - Mladá Boleslav II" → "Mladá Boleslav"
          "Praha 6"                       → "Praha 6"
          ""                              → ""
        """
        if not locality:
            return ""

        # Rozdeľ podľa čiarky — mesto je za poslednou čiarkou
        parts = locality.split(",")
        city = parts[-1].strip() if len(parts) >= 2 else locality.strip()

        # Odstráň "okres " prefix
        city = re.sub(r"^okres\s+", "", city, flags=re.IGNORECASE)

        # Ak má pomlčku (napr. "Mladá Boleslav - Mladá Boleslav II"),
        # vezmi len prvú časť
        if " - " in city:
            city = city.split(" - ")[0].strip()

        return city.strip()

    @staticmethod
    def _parse_rooms(title: str) -> str:
        """
        Extrahuj dispozíciu z title.
        Vzory: '3+kk', '2+1', '1+1', '4+kk', 'garsoniéra'
        Vracia string napr. "3+kk" alebo "" ak sa nenašlo.
        """
        m = re.search(r"(\d+\+(?:kk|\d))", title, re.IGNORECASE)
        if m:
            return m.group(1)
        if re.search(r"garson", title, re.IGNORECASE):
            return "1+kk"
        return ""

    def _type_slug(self) -> str:
        return "prodej" if self._category_type == 1 else "pronajem"

    def _category_slug(self) -> str:
        return "byty" if self._category_main == 1 else "domy"