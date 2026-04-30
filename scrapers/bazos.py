# scrapers/bazos.py — Bazoš.sk scraper

import re
import time

import requests
from bs4 import BeautifulSoup

import config
from scrapers.base import BaseScraper


class BazosScraper(BaseScraper):
    source = "bazos.sk"

    def __init__(self, search_url: str = config.BAZOS_SEARCH_URLS[0]):
        self.search_url = search_url
        import urllib.parse
        params = urllib.parse.parse_qs(urllib.parse.urlparse(search_url).query)
        city = params.get("hlokalita", ["?"])[0]
        self.source = f"bazos.sk/{city}"
        self._session = requests.Session()
        self._session.headers.update(config.REQUEST_HEADERS)

    def fetch(self) -> list[dict]:
        html = self._download(self.search_url)
        if not html:
            return []
        listings = self._parse(html)
        self._log(f"Stiahnutých {len(listings)} inzerátov")
        return listings

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
        for item in soup.select(".inzeraty.inzeratyflex"):
            try:
                listing = self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                self._log(f"Parsing chyba (preskakujem): {e}", "DEBUG")
        return results

    def _parse_item(self, item) -> dict | None:
        # URL + title
        link = item.select_one("h2.nadpis a")
        if not link:
            return None
        title = link.get_text(strip=True)
        url = link.get("href", "")
        if url.startswith("/"):
            url = "https://www.bazos.sk" + url

        inzerat_id = self._extract_id(url)
        if not inzerat_id:
            return None

        # Cena
        cena_tag = item.select_one(".inzeratycena")
        price = self._parse_price(cena_tag.get_text() if cena_tag else "")

        # Lokalita
        lok_tag = item.select_one(".inzeratylok")
        locality = lok_tag.get_text(" ", strip=True) if lok_tag else ""

        # Plocha z titulku + popisu
        popis_tag = item.select_one(".popis")
        popis_text = popis_tag.get_text(" ", strip=True) if popis_tag else ""
        area_m2 = self._extract_area(title + " " + popis_text)
        district = self._extract_district(locality)
        rooms    = self._extract_rooms(title + " " + popis_text)

        return self._make_listing(
            id=inzerat_id,
            title=title,
            url=url,
            price=price,
            area_m2=area_m2,
            locality=locality,
            district=district,
            rooms=rooms,
        )

    @staticmethod
    def _extract_id(url: str) -> str | None:
        m = re.search(r"/inzerat/(\d+)/", url)
        return m.group(1) if m else None

    @staticmethod
    def _parse_price(text: str) -> int:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else 0

    @staticmethod
    def _extract_area(text: str) -> int:
        m = re.search(r"(\d{2,4})\s*m[²2]", text, re.IGNORECASE)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _extract_rooms(text: str) -> int:
        """Extrahuj počet izieb z textu.
        Hľadá vzory: '3-izbový', '2 izb', '1i byt', 'garsónka'
        """
        text = text.lower()
        if "gars" in text:
            return 1
        m = re.search(r"(\d)\s*[-–]?\s*izb", text)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d)\s*i\b", text)
        if m:
            return int(m.group(1))
        return 0

    # Mapa PSČ → mestská časť Bratislava
    _BA_PSC = {
        "811": "Staré Mesto",
        "812": "Staré Mesto",
        "821": "Ružinov",
        "822": "Ružinov",
        "823": "Ružinov",
        "824": "Vrakuňa",
        "825": "Podunajské Biskupice",
        "826": "Podunajské Biskupice",
        "827": "Podunajské Biskupice",
        "831": "Nové Mesto",
        "832": "Nové Mesto",
        "833": "Rača",
        "834": "Vajnory",
        "835": "Vajnory",
        "836": "Záhorská Bystrica",
        "837": "Devínska Nová Ves",
        "838": "Devín",
        "841": "Karlova Ves",
        "842": "Dúbravka",
        "843": "Lamač",
        "844": "Záhorská Bystrica",
        "845": "Záhorská Bystrica",
        "851": "Petržalka",
        "852": "Petržalka",
        "853": "Petržalka",
        "854": "Jarovce",
        "855": "Rusovce",
        "900": "Senec",
        "850": "Petržalka",
        "830": "Nové Mesto",
    }

    @staticmethod
    def _extract_district(locality: str) -> str:
        m = re.search(r"\b(\d{3})\s*\d{2}\b", locality)
        if m:
            prefix = m.group(1)
            return BazosScraper._BA_PSC.get(prefix, "")
        # fallback — pomlčka
        parts = re.split(r"\s*[-–,]\s*", locality, maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""