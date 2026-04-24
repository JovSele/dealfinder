import sys
import time
from datetime import datetime

import config
from scrapers.bazos import BazosScraper
from processing import filters, deal_score
from storage import db
from outputs import telegram

SCRAPERS = [
    BazosScraper(url)
    for url in config.BAZOS_SEARCH_URLS
]

OUTPUTS = [
    telegram,
]


def run_once() -> dict:
    stats = {"scraped": 0, "new": 0, "deals": 0, "alerted": 0}

    for scraper in SCRAPERS:
        listings = scraper.fetch()
        stats["scraped"] += len(listings)

        new_listings = filters.apply(listings)
        stats["new"] += len(new_listings)

        for listing in new_listings:
            db.save_listing(listing)
            db.mark_seen(listing["id"], listing["source"])

            sc = deal_score.score(listing)

            should_alert = deal_score.is_deal(sc) or sc is None
            if should_alert:
                if deal_score.is_deal(sc):
                    stats["deals"] += 1
                for output in OUTPUTS:
                    output.send_alert(listing, sc)
                stats["alerted"] += 1

    return stats


def bootstrap() -> None:
    log("Bootstrap: načítavam existujúce inzeráty...")
    for scraper in SCRAPERS:
        listings = scraper.fetch()
        valid = [l for l in listings if filters.is_valid(l)]
        db.bootstrap_seen(valid)
        for listing in valid:
            db.save_listing(listing)
        log(f"  {scraper.source}: {len(valid)} inzerátov načítaných")
    log("Bootstrap hotový.\n")


def main() -> None:
    log("=" * 50)
    log("  DealFinder — štart")
    log(f"  Scrapers: {[s.source for s in SCRAPERS]}")
    log("=" * 50)

    db.init()

    # GitHub Actions / jednorazové spustenie
    if "--once" in sys.argv:
        log("Režim: --once")
        bootstrap()
        stats = run_once()
        log(f"Hotovo — Nové: {stats['new']} | Dealy: {stats['deals']} | Alerty: {stats['alerted']}")
        return

    # Normálny režim — nekonečná slučka
    log(f"  Interval: {config.SCRAPE_INTERVAL_SEC}s")
    log(f"  DB: {config.DB_PATH}")
    log("=" * 50)

    bootstrap()

    cycle = 0
    while True:
        cycle += 1
        log(f"--- Cyklus #{cycle} ---")
        stats = run_once()
        log(
            f"Stiahnuté: {stats['scraped']} | "
            f"Nové: {stats['new']} | "
            f"Dealy: {stats['deals']} | "
            f"Alerty: {stats['alerted']}"
        )
        log(f"DB celkom: {db.stats()['total_listings']} inzerátov")
        log(f"Ďalší cyklus o {config.SCRAPE_INTERVAL_SEC // 60} min...\n")
        time.sleep(config.SCRAPE_INTERVAL_SEC)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [runner] {msg}")


if __name__ == "__main__":
    main()
