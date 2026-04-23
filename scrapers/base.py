# scrapers/base.py — rozhranie pre všetky scrapers
#
# Každý nový scraper:
#   1. Vytvor súbor scrapers/{zdroj}.py
#   2. Zdedi BaseScraper
#   3. Implementuj fetch()
#   4. Zaregistruj v runner.py → SCRAPERS zoznam
#   Žiadne iné súbory sa nemenia.

from abc import ABC, abstractmethod
from datetime import datetime


class BaseScraper(ABC):
    """Spoločné rozhranie pre všetky scrapers."""

    # Každý scraper musí definovať meno zdroja
    source: str = ""

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Stiahni inzeráty a vráť ich ako zoznam dictov.

        Každý inzerát MUSÍ obsahovať tieto kľúče:
        {
            "id":       str,   # unikátne ID (z URL alebo site ID)
            "title":    str,   # názov inzerátu
            "price":    int,   # cena v EUR, 0 ak neznáma
            "area_m2":  int,   # plocha v m², 0 ak neznáma
            "locality": str,   # lokalita / mesto
            "url":      str,   # priamy link na inzerát
            "source":   str,   # napr. "bazos.sk"
        }

        Výnimky:
            Ak fetch zlyhá, lognuj chybu a vráť prázdny zoznam [].
            Nikdy nenechaj výnimku prebublať do runner.py.
        """

    def _make_listing(
        self,
        id: str,
        title: str,
        url: str,
        price: int = 0,
        area_m2: int = 0,
        locality: str = "",
    ) -> dict:
        """Helper — vytvorí listing dict so správnymi kľúčmi a metadátami."""
        return {
            "id":         id,
            "title":      title.strip(),
            "price":      price,
            "area_m2":    area_m2,
            "locality":   locality.strip(),
            "url":        url,
            "source":     self.source,
            "scraped_at": datetime.now().isoformat(),
        }

    def _log(self, msg: str, level: str = "INFO") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.source}] {msg}")
