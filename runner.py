# runner.py — hlavná slučka, spúšťa všetko
#
# Pridanie nového scrapers:  SCRAPERS.append(NovyScraper())
# Pridanie nového outputu:   OUTPUTS.append(novy_modul)
# Nič iné sa nemení.

import time
from datetime import datetime

import config
from scrapers.bazos import BazosScraper
from processing import filters, deal_score
from storage import db
from outputs import telegram

# ── Registrácia modulov ───────────────────────────────────────
# Sem pridaj nové scrapers / outputs — runner.py sa inak nemení

SCRAPERS = [
    BazosScraper(),
    # NehnutelnostiScraper(),  ← pridáš keď bude hotový
    # SrealityScraper(),
]

OUTPUTS = [
    telegram,
    # email,  ← pridáš keď bude hotový
]


# ── Hlavná slučka ─────────────────────────────────────────────

def run_once() -> dict:
    """Jeden cyklus: scrape → filter → score → alert → save.

    Vracia štatistiky cyklu.
    """
    stats = {"scraped": 0, "new": 0, "deals": 0, "alerted": 0}

    for scraper in SCRAPERS:
        listings = scraper.fetch()
        stats["scraped"] += len(listings)

        # Filtruj — len nové a platné
        new_listings = filters.apply(listings)
        stats["new"] += len(new_listings)

        for listing in new_listings:
            # Ulož do DB (pred alertom — aj keď alert zlyhá, ID ostane)
            db.save_listing(listing)
            db.mark_seen(listing["id"], listing["source"])

            # Vypočítaj Deal Score
            sc = deal_score.score(listing)

            # Alert len pre skutočné dealy (alebo všetky nové ak score nevieme)
            should_alert = deal_score.is_deal(sc) or sc is None
            if should_alert:
                if deal_score.is_deal(sc):
                    stats["deals"] += 1

                for output in OUTPUTS:
                    output.send_alert(listing, sc)

                stats["alerted"] += 1

    return stats


def bootstrap() -> None:
    """Prvý beh — načítaj existujúce inzeráty bez alertov."""
    log("Bootstrap: načítavam existujúce inzeráty...")
    for scraper in SCRAPERS:
        listings = scraper.fetch()
        valid = [l for l in listings if filters.is_valid(l)]
        db.bootstrap_seen(valid)
        for listing in valid:
            db.save_listing(listing)
        log(f"  {scraper.source}: {len(valid)} inzerátov načítaných")
    log("Bootstrap hotový. Spúšťam monitoring...\n")


def main() -> None:
    log("=" * 50)
    log("  DealFinder — štart")
    log(f"  Scrapers: {[s.source for s in SCRAPERS]}")
    log(f"  Interval: {config.SCRAPE_INTERVAL_SEC}s")
    log(f"  DB: {config.DB_PATH}")
    log("=" * 50)

    db.init()
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

        db_stats = db.stats()
        log(f"DB celkom: {db_stats['total_listings']} inzerátov")
        log(f"Ďalší cyklus o {config.SCRAPE_INTERVAL_SEC // 60} min...\n")

        time.sleep(config.SCRAPE_INTERVAL_SEC)


# ── Utils ─────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [runner] {msg}")


if __name__ == "__main__":
    main()
