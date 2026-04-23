# scrapers/bazos.py — Bazoš.sk scraper

import re
import time

import requests
from bs4 import BeautifulSoup

import config
from scrapers.base import BaseScraper


class BazosScraper(BaseScraper):
    source = "bazos.sk"

    def __init__(self, search_url: str = config.BAZOS_SEARCH_URL):
        self.search_url = search_url
        self._session = requests.Session()
        self._session.headers.update(config.REQUEST_HEADERS)

    # ── Public ────────────────────────────────────────────────

    def fetch(self) -> list[dict]:
        html = self._download(self.search_url)
        if not html:
            return []

        listings = self._parse(html)
        self._log(f"Stiahnutých {len(listings)} inzerátov")
        return listings

    # ── Private ───────────────────────────────────────────────

    def _download(self, url: str) -> str | None:
        for attempt in range(1, config.REQUEST_RETRY_COUNT + 1):
            try:
                r = self._session.get(url, timeout=config.REQUEST_TIMEOUT_SEC)
                r.raise_for_status()
                return r.text
            except requests.RequestException as e:
                self._log(f"Pokus {attempt}/{config.REQUEST_RETRY_COUNT} zlyhal: {e}")
                if attempt < config.REQUEST_RETRY_COUNT:
                    time.sleep(config.REQUEST_RETRY_DELAY_SEC)
        return None

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for item in soup.select(".inzeratyzoznam"):
            try:
                listing = self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                self._log(f"Parsing chyba (preskakujem): {e}", "DEBUG")

        return results

    def _parse_item(self, item) -> dict | None:
        # Nazov + URL
        link = item.select_one("h2 a") or item.select_one(".nadpis a")
        if not link:
            return None

        title = link.get_text(strip=True)
        url = link.get("href", "")
        if url.startswith("/"):
            url = "https://www.bazos.sk" + url

        # ID z URL  →  /inzerat/123456/  alebo  ?id=123456
        inzerat_id = self._extract_id(url)
        if not inzerat_id:
            return None

        # Cena
        cena_tag = item.select_one(".inzeratycena")
        price = self._parse_price(cena_tag.get_text() if cena_tag else "")

        # Lokalita + plocha z popisu
        popis_tag = item.select_one(".popis")
        popis_text = popis_tag.get_text(" ", strip=True) if popis_tag else ""
        locality = self._extract_locality(item, popis_text)
        area_m2 = self._extract_area(title + " " + popis_text)

        return self._make_listing(
            id=inzerat_id,
            title=title,
            url=url,
            price=price,
            area_m2=area_m2,
            locality=locality,
        )

    # ── Parsovanie hodnôt ─────────────────────────────────────

    @staticmethod
    def _extract_id(url: str) -> str | None:
        # /inzerat/123456/nazov-bytu/
        m = re.search(r"/inzerat/(\d+)/", url)
        if m:
            return m.group(1)
        # ?id=123456
        m = re.search(r"[?&]id=(\d+)", url)
        if m:
            return m.group(1)
        # fallback: posledný číselný segment
        parts = [p for p in url.rstrip("/").split("/") if p.isdigit()]
        return parts[-1] if parts else None

    @staticmethod
    def _parse_price(text: str) -> int:
        """Extrahuje číslo z textu ako '95 000 €' alebo '95000 EUR'."""
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else 0

    @staticmethod
    def _extract_area(text: str) -> int:
        """Hľadá 'm²' alebo 'm2' v texte, vracia číslo pred ním."""
        m = re.search(r"(\d{2,4})\s*m[²2]", text, re.IGNORECASE)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _extract_locality(item, popis_text: str) -> str:
        # Bazoš má lokalitu v samostatnom elemente
        loc = item.select_one(".inzeratylok") or item.select_one(".lokalita")
        if loc:
            return loc.get_text(strip=True)
        # Fallback: prvé 2 slová z popisu
        words = popis_text.split()
        return " ".join(words[:2]) if words else ""
