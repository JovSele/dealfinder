# scrapers/base.py

from abc import ABC, abstractmethod
from datetime import datetime


class BaseScraper(ABC):
    source: str = ""

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Stiahni inzeráty a vráť ich ako zoznam dictov."""

    def _make_listing(self, **kwargs) -> dict:
        """Helper — vytvor štandardizovaný listing dict."""
        now = datetime.now().isoformat()
        return {
            "id":           kwargs.get("id", ""),
            "source":       kwargs.get("source", self.source),
            "title":        kwargs.get("title", ""),
            "url":          kwargs.get("url", ""),
            "price":        kwargs.get("price", 0),
            "area_m2":      kwargs.get("area_m2", 0),
            "locality":     kwargs.get("locality", ""),
            "district":     kwargs.get("district", ""),
            "rooms":        kwargs.get("rooms", ""),
            "hash":         kwargs.get("hash", ""),
            "scraped_at":   kwargs.get("scraped_at", now),
            "gps_lat":      kwargs.get("gps_lat"),
            "gps_lon":      kwargs.get("gps_lon"),
            "is_auction":   kwargs.get("is_auction", False),
            "new_building": kwargs.get("new_building", False),
            "owner_direct": kwargs.get("owner_direct"),
        }

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.source}] {msg}")
