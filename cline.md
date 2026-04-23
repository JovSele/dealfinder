# Cline Instructions — DealFinder

You are a senior software engineer working on DealFinder — a real estate deal
monitoring service for SK/CZ markets. Your goal is to COMPLETE tasks, not just answer.

---

## Workflow

Always follow PLAN → ACT strictly:

1. **PLAN** — read the relevant existing files first, understand the current state
2. **ACT** — make minimal, targeted changes that fit existing patterns
3. **VERIFY** — check imports, test the change mentally, flag any side effects

Never rewrite working code. Fix root causes, not symptoms. Avoid overengineering.

---

## Project structure

```
dealfinder/
├── config.py              # all settings — tokens, URLs, intervals, thresholds
├── runner.py              # main loop — orchestrates scrapers + processing + outputs
│
├── scrapers/
│   ├── base.py            # BaseScraper ABC — all scrapers implement this interface
│   ├── bazos.py           # Bazoš.sk scraper
│   ├── nehnutelnosti.py   # nehnutelnosti.sk scraper (planned)
│   └── sreality.py        # sreality.cz scraper (planned)
│
├── processing/
│   ├── deal_score.py      # calculates % below market average
│   └── filters.py         # deduplication, blacklist, validation
│
├── storage/
│   ├── db.py              # SQLite wrapper — listings table, seen IDs
│   └── prices.py          # market averages per locality
│
└── outputs/
    ├── telegram.py        # Telegram bot alerts
    └── email.py           # email alerts via Brevo (planned)
```

---

## Core interfaces

Every scraper must extend `BaseScraper` from `scrapers/base.py`:

```python
class BaseScraper:
    def fetch(self) -> list[dict]:
        """Return list of listings. Each listing must have:
        {
            "id": str,          # unique ID (from URL or site ID)
            "title": str,
            "price": int,       # in EUR, 0 if unknown
            "area_m2": int,     # 0 if unknown
            "locality": str,
            "url": str,
            "source": str       # e.g. "bazos.sk"
        }
        """
        raise NotImplementedError
```

Every output module must expose a single function:

```python
def send_alert(listing: dict, score: dict) -> None:
    """Send notification for a new deal.
    score = {"pct_below": float, "avg_price": int, "label": str}
    """
```

---

## Key conventions

- **Config first** — all tokens, URLs, thresholds go in `config.py`. Never hardcode.
- **Fail loudly in dev, silently in prod** — wrap external calls in try/except, log errors, continue.
- **SQLite for now** — `db.py` handles all DB access. No raw SQL outside `db.py`.
- **One scraper = one file** — adding a new source = new file in `scrapers/`, no changes elsewhere.
- **Listings are dicts** — no dataclasses or ORM yet. Keep it simple.
- **Log with print()** — no logging module yet. Format: `[HH:MM:SS] [MODULE] message`

---

## Current state (update this as you build)

- [x] `config.py` — skeleton
- [x] `scrapers/base.py` — interface defined
- [x] `scrapers/bazos.py` — working scraper
- [x] `storage/db.py` — SQLite, listings + seen_ids tables
- [x] `outputs/telegram.py` — alert sending
- [ ] `processing/deal_score.py` — not started
- [ ] `processing/filters.py` — not started
- [ ] `runner.py` — not started
- [ ] `storage/prices.py` — not started
- [ ] `outputs/email.py` — not started

---

## Tech stack

- Python 3.11+
- `requests` + `beautifulsoup4` for scraping
- `sqlite3` (stdlib) for storage
- No frameworks, no ORMs, no async (yet)
- Dependencies: `requests`, `beautifulsoup4` — that's it for now

---

## Business context (why this exists)

DealFinder finds underpriced real estate listings on SK/CZ portals and alerts
subscribers via Telegram. A listing is a "deal" when its price/m² is significantly
below the local market average. Target: €1k–3k/month recurring via subscriptions.

**Deal Score** = how far below market average a listing is, e.g. "−15% pod trhom".
This is the core value proposition — speed + insight over manual searching.

---

## When adding a new scraper

1. Create `scrapers/{source_name}.py`
2. Extend `BaseScraper`, implement `fetch()`
3. Register in `runner.py` — add to `SCRAPERS` list
4. No other files need to change

## When adding a new output channel

1. Create `outputs/{channel}.py`
2. Implement `send_alert(listing, score)`
3. Register in `runner.py` — add to `OUTPUTS` list
4. No other files need to change