# runner.py
import sys
import time
from datetime import datetime

import config
from processing import filters, deal_score
from storage import db
from outputs import telegram
from scrapers.sreality import SrealityScraper

SCRAPERS = [
   
    # --- Czech market ---
    SrealityScraper(source="sreality/byty", category_main_cb=1, category_type_cb=1, region_id=11),
    SrealityScraper(source="sreality/domy", category_main_cb=2, category_type_cb=1, region_id=11),

    # --- Praha ---
    SrealityScraper(source="sreality/byty/praha", category_main_cb=1, category_type_cb=1, region_id=10),
    SrealityScraper(source="sreality/domy/praha", category_main_cb=2, category_type_cb=1, region_id=10),
]


OUTPUTS = [
    telegram,
]

LOOP_INTERVAL_SEC = 20 * 60  # 20 minút


def run_once() -> dict:
    stats = {"scraped": 0, "new": 0, "deals": 0, "alerted": 0}

    for scraper in SCRAPERS:
        listings = scraper.fetch()
        stats["scraped"] += len(listings)

        new_listings = filters.apply(listings)
        stats["new"] += len(new_listings)

        scored = []
        for listing in new_listings:
            db.save_listing(listing)
            db.mark_seen(listing["id"], listing["source"])
            sc = deal_score.score(listing)
            if deal_score.is_deal(sc):
                scored.append((listing, sc))

        for listing, sc in filters.top_deals(scored):
            stats["deals"] += 1
            for output in OUTPUTS:
                output.send_alert(listing, sc)
            stats["alerted"] += 1

    return stats

FREE_ALERTS_PER_DAY = 3

def send_pending_free_alerts() -> int:
    pending = db.get_pending_free_alerts(delay_hours=config.FREE_DELAY_HOURS)
    if not pending:
        return 0

    from processing import deal_score as ds

    already_sent_today = db.get_free_sent_today_count()
    remaining = max(0, FREE_ALERTS_PER_DAY - already_sent_today)

    deals_only = []
    to_skip = []

    for listing in pending:
        try:
            sc = ds.score(listing)
            if ds.is_deal(sc) and len(deals_only) < remaining:
                listing["_score"] = sc
                deals_only.append(listing)
            else:
                to_skip.append(listing)
        except Exception:
            to_skip.append(listing)

    # Označ non-dealy a prebytočné dealy ako spracované (bez odoslania)
    for listing in to_skip:
        db.mark_free_sent(listing["id"], listing["source"])

    log(f"Free kanál: dnes už {already_sent_today}/3, posielam {len(deals_only)}")

    sent = 0
    for listing in deals_only:
        sc = listing.pop("_score", None)
        telegram.send_free_alert(listing, sc)
        db.mark_free_sent(listing["id"], listing["source"])
        sent += 1

    return sent

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

    if "--weekly" in sys.argv:
        log("Režim: --weekly summary")

        deals = db.get_weekly_deals()
        telegram.send_weekly_free_summary(deals)

        count = len(deals)
        if count:
            log(f"Weekly summary odoslaný — {count} dealy tento týždeň")
            telegram.send_admin(f"📊 *Weekly summary odoslaný* — {count} dealy")
        else:
            log("Weekly summary preskočený — žiadne dealy tento týždeň")
            telegram.send_admin("📊 *Weekly summary preskočený* — 0 dealy tento týždeň")
        return

    # Jednorazové spustenie
    if "--once" in sys.argv:
        log("Režim: --once")

        # Bootstrap len ak je DB nová (prázdna)
        if db.stats()["total_seen"] == 0:
            log("Prázdna DB — spúšťam bootstrap")
            bootstrap()
        else:
            log(f"DB existuje — bootstrap preskakujem")

        try:
            stats = run_once()
            free_sent = send_pending_free_alerts()
            log(
                f"Hotovo — Nové: {stats['new']} | Dealy: {stats['deals']} | "
                f"Alerty: {stats['alerted']} | Free odoslané: {free_sent}"
            )
            telegram.send_run_summary(stats, free_sent)
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            log(f"CHYBA: {err}")
            telegram.send_admin(f"🔴 *DealFinder CRASH*\n```\n{err[:300]}\n```")
            raise

        return

    # Nekonečná slučka — každých 20 minút
    if "--loop" in sys.argv:
        log(f"Režim: --loop (každých {LOOP_INTERVAL_SEC // 60} minút)")
        log("=" * 50)

        if db.stats()["total_seen"] == 0:
            log("Prázdna DB — spúšťam bootstrap")
            bootstrap()
        else:
            log("DB existuje — bootstrap preskakujem")

        cycle = 0
        while True:
            cycle += 1
            log(f"--- Cyklus #{cycle} ---")
            try:
                stats = run_once()
                free_sent = send_pending_free_alerts()
                log(
                    f"Stiahnuté: {stats['scraped']} | "
                    f"Nové: {stats['new']} | "
                    f"Dealy: {stats['deals']} | "
                    f"Alerty: {stats['alerted']} | "
                    f"Free: {free_sent}"
                )
                log(f"DB celkom: {db.stats()['total_listings']} inzerátov")
                telegram.send_run_summary(stats, free_sent)
            except Exception as e:
                import traceback
                err = traceback.format_exc()
                log(f"CHYBA v cykle #{cycle}: {err}")
                telegram.send_admin(f"🔴 *DealFinder CHYBA* (cyklus #{cycle})\n```\n{err[:1000]}\n```")

            log(f"Ďalší cyklus o {LOOP_INTERVAL_SEC // 60} min...\n")
            time.sleep(LOOP_INTERVAL_SEC)

        return

    log("Použi --once alebo --loop")
    log("  --once   jednorazové spustenie")
    log("  --loop   nekonečná slučka každých 20 minút")
    log("  --weekly týždenný súhrn")


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [runner] {msg}")


if __name__ == "__main__":
    main()
