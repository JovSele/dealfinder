# Product Status — DealFinder
_Last updated: 2026-04-28_

---

## What this product does (1 paragraph)

DealFinder monitors Slovak real estate classified portals (currently bazos.sk) for newly listed apartments, computes a "Deal Score" that measures how far below the local market average a listing is priced per m², and pushes instant Telegram alerts to paying subscribers. There are two Telegram channels: a **paid (Premium)** channel that receives alerts immediately, and a **free** channel that receives the same alerts with a configurable delay (default 24 h). Access to the paid channel is sold via Gumroad (€/month) and managed by a separate subscription bot (`bot.py`). The business goal is €1k–3k/month recurring revenue from subscriptions.

---

## Architecture overview

| Component | File(s) | What it does |
|---|---|---|
| **Config** | `config.py` | Single source of truth for all tokens, URLs, thresholds, intervals. Reads from `.env` / environment variables via `python-dotenv`. |
| **Scraper base** | `scrapers/base.py` | Abstract base class `BaseScraper`. Defines the `fetch() → list[dict]` contract, shared `_make_listing()` helper, and `_log()` utility. |
| **Bazos.sk scraper** | `scrapers/bazos.py` | `BazosScraper` — fetches apartment listings from bazos.sk for 4 Slovak cities (Bratislava, Košice, Žilina, Nitra). Parses HTML with BeautifulSoup. Extracts: ID, title, price, area m², locality, district (via PSČ map), room count. Has retry logic (3 attempts, 5 s delay). |
| **Filters** | `processing/filters.py` | Two-stage pipeline: `is_valid()` (validates id/url/title, rejects price < `FILTER_MIN_PRICE_EUR`) → `is_new()` (DB dedup check). `apply()` runs both stages on a list. |
| **Deal Score** | `processing/deal_score.py` | `score()` calculates `pct_below` = how many % below local average price/m² the listing is. Requires at least `DEAL_SCORE_MIN_SAMPLES` (default 5) comparables in DB. Returns `None` when insufficient data. `is_deal()` checks against `DEAL_SCORE_THRESHOLD_PCT` (default 10%). |
| **Database** | `storage/db.py` | SQLite wrapper. Three tables: `listings` (all seen listings), `seen_ids` (dedup set), `free_sent` (tracks what was sent to free channel). Key functions: `init()`, `save_listing()`, `mark_seen()`, `bootstrap_seen()`, `get_pending_free_alerts()`, `mark_free_sent()`, `stats()`. |
| **Telegram output** | `outputs/telegram.py` | `send_alert(listing, score)` → paid channel. `send_free_alert(listing, score)` → free channel (adds ⏰ badge + upsell hint). Uses raw HTTP via `requests` to the Telegram Bot API (no telegram library). |
| **Runner** | `runner.py` | Main orchestrator. `bootstrap()` seeds seen_ids on first run to prevent alert floods. `run_once()` iterates all scrapers → filters → score → alert. `send_pending_free_alerts()` drains delayed free-channel queue. Supports `--once` flag (used by GitHub Actions) and infinite loop mode. |
| **Subscription bot** | `bot.py` | Separate `python-telegram-bot` application. Handles `/start` (registers user, issues one-time channel invite link), `/status` (shows subscription expiry). Daily job at 09:00 UTC: sends 3-day expiry warnings, bans+unbans expired members from the paid channel. Uses its own `members.db`. |
| **GitHub Actions** | `.github/workflows/scraper.yml` | Cron job every 20 minutes. Checks out code, downloads `dealfinder.db` artifact from previous run (so dedup persists), runs `python runner.py --once`, uploads updated DB artifact (7-day retention). |
| **Sreality prototype** | `Sreality pipeline.py` | **Standalone, unintegrated** prototype for sreality.cz (Czech market). Hardcoded tokens. Stores seen IDs in JSON. Not used by runner.py. |
| **Debug artifact** | `debug.html` | Raw HTML dump of a bazos.sk results page. Used during scraper development to test parsing without network calls. Dead file in production. |

---

## Current working features

- **Bazos.sk scraping**: `BazosScraper.fetch()` is fully implemented. Scrapes 4 city URLs, parses listings including price, area, locality, district (PSČ map for Bratislava neighbourhoods), and room count.
- **Deduplication**: `seen_ids` table + `bootstrap_seen()` correctly prevents alert floods on startup and across GitHub Actions runs (via artifact persistence).
- **Deal Score calculation**: Compares listing's €/m² against local average from DB. Returns structured result with `pct_below`, `price_per_m2`, `avg_per_m2`, `label`, `sample_size`. Returns `None` gracefully when < 5 comparables.
- **Telegram paid channel alerts**: `send_alert()` is functional. Formats Markdown message with emoji, price, area, deal score, locality, source link.
- **Telegram free channel alerts**: `send_free_alert()` is functional. Adds delay badge and upsell line.
- **Free channel delay pipeline**: `get_pending_free_alerts()` + `mark_free_sent()` + `send_pending_free_alerts()` in runner correctly implements the 24 h delay logic.
- **Subscription bot**: `/start` creates one-time invite links. `/status` shows days remaining. Daily expiry check bans expired users and sends renewal reminders.
- **GitHub Actions automation**: Scraper runs every 20 minutes. DB artifact persists dedup state across runs.
- **Configurable thresholds**: All key parameters (price floor, deal threshold %, min samples, delay hours, scrape interval) are env-var driven via `config.py`.

---

## Broken / incomplete / TODO

### Critical

1. **`bot.py` crashes if `CHANNEL_ID` env var is missing** — line 30: `CHANNEL_ID = int(os.getenv("CHANNEL_ID"))` — `os.getenv()` returns `None` when unset, and `int(None)` raises `TypeError`. No default value provided. The bot will not start if this env var is absent.

2. **`TELEGRAM_FREE_CHAT_ID` not injected by GitHub Actions** — `.github/workflows/scraper.yml` only sets `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`. `TELEGRAM_FREE_CHAT_ID` is missing from the `env:` block (line 29–32). Free channel alerts are silently skipped in every GHA run (`outputs/telegram.py` line 36–37: `_log("TELEGRAM_FREE_CHAT_ID nie je nastavený — preskakujem free alert")`).

3. **DB artifact retention is only 7 days** — `scraper.yml` line 40: `retention-days: 7`. If the Actions runner fails or is paused for more than 7 days, the `dealfinder.db` artifact is deleted. On next run, `bootstrap_seen()` will re-mark all current listings as seen (no flood), but all accumulated Deal Score comparables are lost and scoring will return `None` for all listings until the DB rebuilds (requires ≥ 5 listings per locality per source).

4. **`_extract_district` defined twice in `BazosScraper`** (`scrapers/bazos.py` lines 98–106 and 173–181). Python's method resolution silently uses the second definition (PSČ-based lookup with `_BA_PSC` dict). The first definition (split on dash/comma) is dead code but creates a false sense that both approaches coexist.

### Significant

5. **Deal Score compares listing against itself** — in `runner.py` `run_once()`, `db.save_listing(listing)` is called (line 33) *before* `deal_score.score(listing)` (line 36). The listing is now in DB and included in `get_listings_by_locality()` comparables, slightly biasing the average toward the listing being scored. Should score *before* saving, or exclude the current listing from comparables.

6. **All listings with `sc is None` are alerted** — `runner.py` line 38: `should_alert = deal_score.is_deal(sc) or sc is None`. In early operation (DB has < 5 listings per locality), *every* new listing generates an alert. This is acceptable for bootstrapping but will cause noise at scale. There is no configurable flag to disable this behaviour.

7. **`Sreality pipeline.py` is completely unintegrated** — has hardcoded `TELEGRAM_TOKEN = "VAS_BOT_TOKEN"` (line 27) and `TELEGRAM_CHAT_ID = "VAS_CHAT_ID"` (line 28), uses JSON files for dedup, prices are in CZK (not EUR), and it operates on Prague/Czech regions. The filename has a **space** in it, making it un-importable as a Python module. It is a throwaway prototype that has not been ported to the modular architecture.

8. **`bot.py` is never started by GitHub Actions** — the subscription bot requires a long-running process (`app.run_polling()`). There is no GitHub Actions workflow, Dockerfile, or deployment config for it. It must be run manually or on a separate always-on server. No instructions exist for this.

9. **`cline.md` is severely out of date** — lines 98–101 mark `processing/deal_score.py`, `processing/filters.py`, `storage/prices.py`, and `runner.py` as "not started", but all of these (except `prices.py`) are fully implemented. This document will actively mislead a new contributor.

### Minor

10. **Price formatting inconsistency in `outputs/telegram.py`** — line 83 formats price with space separator: `f"{price:,} €".replace(",", " ")`. Lines 95–96 format score prices with comma: `f"{score['price_per_m2']:,} €/m²"` — no replacement. Results in mixed separators (space vs comma) in the same Telegram message.

11. **`BAZOS_SEARCH_URL` alias in `config.py` line 29** — `BAZOS_SEARCH_URL = BAZOS_SEARCH_URLS[0]` is declared as a "backwards compatibility" alias but is not referenced anywhere in the current codebase.

12. **`debug.html`** — a 591-line raw HTML dump of bazos.sk sitting in the project root. Should be deleted or moved to a `tests/fixtures/` directory.

13. **`storage/prices.py` does not exist** — referenced in `cline.md` as planned. Deal Score currently derives averages from accumulated listing history in the `listings` table, which works but means the score is meaningless until enough listings have been scraped per locality.

14. **`outputs/email.py` does not exist** — referenced in `cline.md` as planned. Email alerting channel is missing.

15. **`scrapers/nehnutelnosti.py` and `scrapers/sreality.py` do not exist** — referenced in `cline.md` as planned scrapers. Only bazos.sk is currently scraped.

---

## Data flow (step by step)

```
1. GitHub Actions cron fires every 20 minutes
   └─ .github/workflows/scraper.yml

2. Checkout repo + install requirements
   └─ requests, beautifulsoup4, python-dotenv, python-telegram-bot[job-queue]

3. Download 'dealfinder-db' artifact from previous run → dealfinder.db
   └─ Provides dedup history. First run: artifact missing (continue-on-error: true)

4. python runner.py --once
   └─ runner.main()

5. db.init() → creates tables if not exist
   └─ storage/db.py: listings, seen_ids, free_sent tables

6. bootstrap()
   └─ For each BazosScraper (4 city URLs):
       a. scraper.fetch() → HTTP GET bazos.sk with realistic User-Agent + retry logic
       b. Parse HTML with BeautifulSoup (css selector .inzeraty.inzeratyflex)
       c. Extract: id, title, price, area_m2, locality, district, rooms, url, source
       d. filters.is_valid() on each → reject if missing id/url/title or price < 10,000 €
       e. db.bootstrap_seen(valid_listings) → INSERT OR IGNORE into seen_ids + free_sent
          (prevents flood on first run and prevents free-channel re-alerting bootstrapped items)
       f. db.save_listing() for each valid listing → INSERT OR IGNORE into listings

7. run_once()
   └─ For each BazosScraper:
       a. scraper.fetch() → same HTTP scrape as step 6
       b. filters.apply(listings):
           - is_valid(): validate fields, price floor
           - is_new(): db.is_new() → checks seen_ids table
           → returns only valid + previously-unseen listings
       c. For each new listing:
           i.  db.save_listing(listing) → persist to listings table
           ii. db.mark_seen(id, source) → add to seen_ids
           iii. deal_score.score(listing):
                - retrieve comparables: db.get_listings_by_locality(locality, source)
                - filter comparables with area_m2 > 0, price > 0
                - if < 5 comparables → return None
                - compute avg_per_m2 = mean(price/area_m2 for all comparables)
                - pct_below = (avg - listing_per_m2) / avg * 100
                - return dict {pct_below, price_per_m2, avg_per_m2, label, sample_size}
           iv. should_alert = is_deal(score) OR score is None
           v.  If should_alert:
                telegram.send_alert(listing, score)
                └─ HTTP POST to api.telegram.org/bot{TOKEN}/sendMessage
                   chat_id = TELEGRAM_CHAT_ID (paid channel)
                   Markdown formatted message with emoji, price, area, score, locality, link

8. send_pending_free_alerts()
   └─ db.get_pending_free_alerts(delay_hours=24)
       SQL: JOIN listings + seen_ids + LEFT JOIN free_sent
            WHERE free_sent.id IS NULL
              AND seen_ids.first_seen <= NOW - 24h
   └─ For each pending:
       a. deal_score.score(listing) → likely None (listing is old, from DB dict)
       b. telegram.send_free_alert(listing, score)
          └─ HTTP POST to TELEGRAM_FREE_CHAT_ID (free channel)
             ⚠️ CURRENTLY BROKEN: TELEGRAM_FREE_CHAT_ID not set in GHA env
       c. db.mark_free_sent(id, source)

9. Upload updated dealfinder.db as artifact (7-day retention)
   └─ Next run downloads this artifact to preserve dedup + scoring history
```

---

## External dependencies

| Dependency | Purpose | Configured? |
|---|---|---|
| `TELEGRAM_TOKEN` | Bot API token for sending alerts (both channels use same token) | Set as GitHub Actions secret. Also needed for `bot.py` as `BOT_TOKEN`. |
| `TELEGRAM_CHAT_ID` | Paid channel ID | Set as GitHub Actions secret. |
| `TELEGRAM_FREE_CHAT_ID` | Free channel ID | **NOT set in GitHub Actions workflow** — must be added to `scraper.yml` env block and GitHub Secrets. |
| `BOT_TOKEN` | `bot.py`'s own bot token (may be same as `TELEGRAM_TOKEN`) | Not in GHA. Must be set manually wherever `bot.py` runs. |
| `CHANNEL_ID` | Paid channel ID for `bot.py` invite link creation | Not in GHA. Required for bot, crashes if missing. |
| `DB_PATH` | SQLite database path | Set to `dealfinder.db` in GHA workflow. |
| `DEAL_SCORE_THRESHOLD_PCT` | Minimum % below market to qualify as deal | Optional, defaults to `10.0`. |
| `DEAL_SCORE_MIN_SAMPLES` | Min comparables required to compute score | Optional, defaults to `5`. |
| `FILTER_MIN_PRICE_EUR` | Minimum price to accept a listing | Optional, defaults to `10000`. |
| `FREE_DELAY_HOURS` | Hours delay before free channel alert | Optional, defaults to `24`. |
| `SCRAPE_INTERVAL_SEC` | Loop interval (loop mode only, not GHA) | Optional, defaults to `300`. |
| `DAYS_ACCESS` | Subscription duration in days (`bot.py`) | Optional, defaults to `30`. |
| `LOG_LEVEL` | Logging level (currently unused — all output via `print()`) | Optional, defaults to `INFO`. |
| **Gumroad** | Payment processor (`RENEWAL_LINK` hardcoded in `bot.py` line 34) | Hardcoded URL `https://dealfinderalerts.gumroad.com/l/pwcgi` |
| **bazos.sk** | Data source | No API key needed. Uses browser-like headers. Subject to HTML structure changes. |
| **GitHub Actions** | Scheduler + ephemeral runner | Active — `dawidd6/action-download-artifact@v6` used for DB persistence. |
| **python-telegram-bot** | Used only in `bot.py` for subscription management | Not used in `runner.py` (which uses raw `requests`). |

---

## Known issues / tech debt

1. **`bot.py` has no deployment home.** There is no `Dockerfile`, `Procfile`, `systemd` unit, or hosting instructions. The bot runs with long polling (`app.run_polling()`), requiring a persistent process. As-is it would need to be run manually on a VPS or Heroku-equivalent.

2. **DB persistence via GitHub Actions artifact is fragile.** The 7-day artifact retention means the entire history (dedup + market averages) vanishes if scraping pauses for a week. The correct solution is to persist the DB to an external store (e.g., S3, Supabase, or a mounted volume).

3. **Single-page scraping only.** `BazosScraper.fetch()` downloads only one search results page per URL (the first ~20 listings). No pagination is implemented. High-volume cities like Bratislava have 3,567+ listings per category. New listings that push existing ones off page 1 within 20 minutes will be missed.

4. **No pagination means Deal Score comparables are sparse.** Market averages are only built from whatever happens to appear on page 1 across repeated runs. Score quality is low until the DB accumulates sufficient history.

5. **`Sreality pipeline.py` is dead weight.** Filename with a space is non-standard. Tokens are hardcoded placeholders. Logic is not compatible with the modular architecture. Should either be properly ported to `scrapers/sreality.py` or deleted.

6. **`RENEWAL_LINK` is hardcoded in `bot.py` line 34** — `"https://dealfinderalerts.gumroad.com/l/pwcgi"`. Should be moved to `config.py` as an env var.

7. **No error alerting.** If the GitHub Actions run fails (network timeout, bazos.sk blocks, Telegram rate limit), it fails silently. No notification to the operator.

8. **`run_once()` scores after saving** — listing is included in its own comparables pool, creating a small self-reference bias in the market average calculation.

9. **Bazos.sk HTML structure is fragile.** Parser relies on CSS selectors `.inzeraty.inzeratyflex`, `h2.nadpis`, `.inzeratycena`, `.inzeratylok`, `.popis`. Any HTML change on bazos.sk silently returns 0 results (no error thrown, `_log` only).

10. **No test suite.** Zero unit or integration tests. `debug.html` exists as a manual testing artifact but is not wired to any test runner.

11. **`cline.md` is the only internal documentation** and is stale (marks implemented modules as "not started"). It will mislead the next developer.

12. **Two separate SQLite databases** — `runner.py` uses `dealfinder.db` (listings, dedup, free_sent). `bot.py` uses `members.db` (subscription management). These are completely independent; there is no link between subscriber IDs and alert delivery — alerts are pushed to channels, not to individual users.

---

## What to build next (priority order)

1. **Fix `TELEGRAM_FREE_CHAT_ID` in GitHub Actions workflow** _(~5 min fix)_
   Add `TELEGRAM_FREE_CHAT_ID: ${{ secrets.TELEGRAM_FREE_CHAT_ID }}` to `scraper.yml`'s `env:` block and add the secret in GitHub repository settings. Free channel is fully coded — it just needs the env var.

2. **Implement pagination in `BazosScraper`** _(high impact)_
   The current scraper sees only ~20 listings per city per run. Bazos.sk paginates in increments of 20 (`/20/?...`, `/40/?...`). A scraper that stops when it hits a `seen_id` (or reaches N pages) would capture the full new-listings tail and build meaningful Deal Score comparables faster.

3. **Persist the SQLite DB to external storage** _(reliability)_
   Replace the 7-day artifact approach with an S3 bucket upload/download (or equivalent). This makes the dedup and scoring history durable. AWS S3 free tier, Cloudflare R2, or a simple VPS with rsync would all work.

4. **Deploy `bot.py` to a persistent host** _(business-critical)_
   The subscription management bot needs to run 24/7. Options: Fly.io, Railway, a €5/month VPS. Add a `Dockerfile` and deployment instructions. Also fix the `CHANNEL_ID` crash (add a sensible default or a startup check).

5. **Add a second scraper (nehnutelnosti.sk or sreality.sk)** _(growth)_
   The architecture fully supports it — create `scrapers/nehnutelnosti.py`, extend `BaseScraper`, add to `SCRAPERS` in `runner.py`. The existing `Sreality pipeline.py` contains working API scraping logic for sreality.cz and can be ported. More sources = richer comparables for Deal Score = better product.

---

## File map

| File | Description |
|---|---|
| `config.py` | All configuration — Telegram tokens/chat IDs, bazos.sk search URLs, request headers/timeouts/retries, DB path, deal score thresholds, free delay hours, log level. Reads from `.env` or env vars. |
| `runner.py` | Main orchestrator. `main()` entry point; `bootstrap()` seeds DB on first run; `run_once()` drives the scrape→filter→score→alert pipeline; `send_pending_free_alerts()` handles delayed free-channel delivery. |
| `bot.py` | Telegram subscription management bot. Handles `/start` (register user + send channel invite), `/status` (show expiry), and a daily job to warn expiring / kick expired members. Completely separate process from `runner.py`. |
| `scrapers/base.py` | `BaseScraper` ABC. Defines `fetch()` contract, `_make_listing()` helper (builds standardized listing dict with md5 content hash), and `_log()`. |
| `scrapers/bazos.py` | `BazosScraper`. Scrapes bazos.sk search results page for 4 Slovak cities. Parses HTML with BeautifulSoup. Includes PSČ → Bratislava district map, room count extraction, area extraction. Has retry logic. |
| `scrapers/__init__.py` | Empty — marks directory as Python package. |
| `processing/deal_score.py` | `score(listing)` — computes Deal Score (% below local market average €/m²) using DB comparables. `is_deal(score)` — threshold check. `_label()` — human-readable string with emoji. |
| `processing/filters.py` | `is_valid()` — validates listing fields and price floor. `is_new()` — DB dedup check. `apply()` — runs both filters on a list and logs rejections. |
| `processing/__init__.py` | Empty — marks directory as Python package. |
| `storage/db.py` | SQLite wrapper. Schema: `listings`, `seen_ids`, `free_sent`. Functions: `init()`, `save_listing()`, `get_listings_by_locality()`, `is_new()`, `mark_seen()`, `bootstrap_seen()`, `get_pending_free_alerts()`, `mark_free_sent()`, `stats()`. |
| `storage/__init__.py` | Empty — marks directory as Python package. |
| `outputs/telegram.py` | `send_alert()` → paid channel. `send_free_alert()` → free channel (with delay badge). `_format_message()` — builds Markdown message. `_send()` — HTTP POST to Telegram Bot API. |
| `outputs/__init__.py` | Empty — marks directory as Python package. |
| `.github/workflows/scraper.yml` | GitHub Actions cron (every 20 min). Downloads DB artifact → runs `python runner.py --once` → uploads updated DB artifact. Missing `TELEGRAM_FREE_CHAT_ID` env var. |
| `Sreality pipeline.py` | **Unintegrated standalone prototype** for sreality.cz (Prague). Hardcoded bot tokens, CZK prices, JSON-based dedup. Not used by runner.py. Filename has a space — cannot be imported. |
| `requirements.txt` | `requests`, `beautifulsoup4`, `python-dotenv`, `python-telegram-bot[job-queue]==21.5`. |
| `cline.md` | Cline AI instructions and architecture notes. **Stale** — marks implemented modules as incomplete. |
| `debug.html` | Raw HTML dump of a bazos.sk results page (591 lines). Used for manual scraper testing. Dead file — should be deleted or moved to `tests/fixtures/`. |
| `README.md` | Minimal — just git commands and `python runner.py --once`. No setup instructions, no env var documentation. |
| `.gitignore` | Ignores `.env`, `*.db`, `__pycache__`, `.pyc`, `.DS_Store`, `venv/`, `.venv/`. |
