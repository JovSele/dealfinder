# storage/db.py — jediné miesto kde sa dotýkame databázy
#
# Tabuľky:
#   listings      — každý inzerát čo sme kedy videli
#   seen_ids      — rýchla množina pre is_new() check
#   free_sent     — inzeráty ktoré už boli poslané do Free kanála
#   price_history — história cien inzerátov

import os
from contextlib import contextmanager
from datetime import datetime

import psycopg2
import psycopg2.extras
import psycopg2.errors

DATABASE_URL = os.getenv("DATABASE_URL", "")


# ── Schéma ────────────────────────────────────────────────────

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS listings (
        id              TEXT NOT NULL,
        source          TEXT NOT NULL,
        title           TEXT,
        price           INTEGER DEFAULT 0,
        area_m2         INTEGER DEFAULT 0,
        locality        TEXT,
        district        TEXT DEFAULT '',
        rooms           TEXT DEFAULT '',
        hash            TEXT DEFAULT '',
        url             TEXT,
        scraped_at      TEXT,
        -- nové stĺpce
        floor           INTEGER DEFAULT NULL,
        floor_total     INTEGER DEFAULT NULL,
        building_type   TEXT DEFAULT NULL,
        condition       TEXT DEFAULT NULL,
        energy_class    TEXT DEFAULT NULL,
        has_elevator    BOOLEAN DEFAULT NULL,
        has_balcony     BOOLEAN DEFAULT NULL,
        has_parking     BOOLEAN DEFAULT NULL,
        has_terrace     BOOLEAN DEFAULT NULL,
        ownership_type  TEXT DEFAULT NULL,
        is_auction      BOOLEAN DEFAULT FALSE,
        new_building    BOOLEAN DEFAULT FALSE,
        owner_direct    BOOLEAN DEFAULT NULL,
        gps_lat         REAL DEFAULT NULL,
        gps_lon         REAL DEFAULT NULL,
        price_first_seen INTEGER DEFAULT NULL,
        enriched        BOOLEAN DEFAULT FALSE,
        PRIMARY KEY (id, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS seen_ids (
        id          TEXT NOT NULL,
        source      TEXT NOT NULL,
        first_seen  TEXT NOT NULL,
        PRIMARY KEY (id, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS free_sent (
        id          TEXT NOT NULL,
        source      TEXT NOT NULL,
        sent_at     TEXT NOT NULL,
        PRIMARY KEY (id, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price_history (
        id          TEXT NOT NULL,
        source      TEXT NOT NULL,
        price       INTEGER NOT NULL,
        recorded_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_listings_locality
        ON listings(locality, source)
    """,
]

# Migrácie — každá sa pokúsi raz, pri chybe (stĺpec už existuje) ticho preskočí
MIGRATIONS = [
    "ALTER TABLE listings ADD COLUMN district TEXT DEFAULT ''",
    "ALTER TABLE listings ADD COLUMN rooms    TEXT DEFAULT ''",
    "ALTER TABLE listings ADD COLUMN hash     TEXT DEFAULT ''",
    "ALTER TABLE listings ADD COLUMN floor          INTEGER DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN floor_total    INTEGER DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN building_type  TEXT DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN condition       TEXT DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN energy_class   TEXT DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN has_elevator   BOOLEAN DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN has_balcony    BOOLEAN DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN has_parking    BOOLEAN DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN has_terrace    BOOLEAN DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN ownership_type TEXT DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN is_auction     BOOLEAN DEFAULT FALSE",
    "ALTER TABLE listings ADD COLUMN new_building   BOOLEAN DEFAULT FALSE",
    "ALTER TABLE listings ADD COLUMN owner_direct   BOOLEAN DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN gps_lat        REAL DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN gps_lon        REAL DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN price_first_seen INTEGER DEFAULT NULL",
    "ALTER TABLE listings ADD COLUMN enriched       BOOLEAN DEFAULT FALSE",
]


# ── Connection ────────────────────────────────────────────────

@contextmanager
def _conn():
    con = psycopg2.connect(DATABASE_URL)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Internal helpers ──────────────────────────────────────────

def _execute(con, query: str, params: tuple = ()) -> None:
    with con.cursor() as cur:
        cur.execute(query, params)


def _executemany(con, query: str, params_list) -> None:
    with con.cursor() as cur:
        cur.executemany(query, params_list)


def _fetchall(con, query: str, params: tuple = ()) -> list[dict]:
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def _fetchone(con, query: str, params: tuple = ()):
    """Returns first row as dict, or None."""
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _fetchscalar(con, query: str, params: tuple = ()):
    """Returns first column of first row (for COUNT queries etc.)."""
    with con.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else None

def update_enrichment(listing_id: str, source: str, data: dict) -> None:
    """Aktualizuj stĺpce z detail endpointu."""
    with _conn() as con:
        _execute(
            con,
            """
            UPDATE listings SET
                floor          = %(floor)s,
                floor_total    = %(floor_total)s,
                building_type  = %(building_type)s,
                condition      = %(condition)s,
                energy_class   = %(energy_class)s,
                has_elevator   = %(has_elevator)s,
                has_balcony    = %(has_balcony)s,
                has_parking    = %(has_parking)s,
                has_terrace    = %(has_terrace)s,
                ownership_type = %(ownership_type)s,
                enriched       = TRUE
            WHERE id = %(id)s AND source = %(source)s
            """,
            {**data, "id": listing_id, "source": source},
        )

def get_unenriched(limit: int = 50) -> list[dict]:
    """Vráti listingy ktoré ešte nemajú detail dáta."""
    with _conn() as con:
        return _fetchall(
            con,
            """
            SELECT id, source FROM listings
            WHERE enriched = FALSE AND source LIKE 'sreality%'
            ORDER BY scraped_at DESC
            LIMIT %s
            """,
            (limit,),
        )


# ── Init ──────────────────────────────────────────────────────

def init():
    """Vytvor tabuľky ak neexistujú + spusti migrácie."""
    with _conn() as con:
        for stmt in _SCHEMA_STATEMENTS:
            _execute(con, stmt)

    for migration in MIGRATIONS:
        try:
            with _conn() as con:
                _execute(con, migration)
        except Exception:
            pass  # stĺpec už existuje — ignoruj

    _cleanup_legacy_sources()


def _cleanup_legacy_sources():
    legacy = ("sreality_byty", "sreality_domy")
    try:
        with _conn() as con:
            for source in legacy:
                count = _fetchscalar(con, "SELECT COUNT(*) FROM listings WHERE source = %s", (source,))
                if count and count > 0:
                    _execute(con, "DELETE FROM listings  WHERE source = %s", (source,))
                    _execute(con, "DELETE FROM seen_ids  WHERE source = %s", (source,))
                    _execute(con, "DELETE FROM free_sent WHERE source = %s", (source,))
                    print(f"[db] Cleanup: zmazaných {count} legacy záznamov ({source})")
    except Exception:
        pass  # tabuľky ešte neexistujú — ignoruj

# ── Listings ──────────────────────────────────────────────────

# OPRAV TOTO — použi RETURNING aby si vedel či bol INSERT skutočný:
def save_listing(listing: dict) -> None:
    now = datetime.now().isoformat()
    with _conn() as con:
        result = _fetchone(
            con,
            """
            INSERT INTO listings (
                id, source, title, price, area_m2, locality, district, rooms, hash, url, scraped_at,
                is_auction, new_building, owner_direct, gps_lat, gps_lon, price_first_seen, enriched
            ) VALUES (
                %(id)s, %(source)s, %(title)s, %(price)s, %(area_m2)s, %(locality)s,
                %(district)s, %(rooms)s, %(hash)s, %(url)s, %(scraped_at)s,
                %(is_auction)s, %(new_building)s, %(owner_direct)s,
                %(gps_lat)s, %(gps_lon)s, %(price)s, FALSE
            )
            ON CONFLICT (id, source) DO NOTHING
            RETURNING id
            """,
            {
                "is_auction":   listing.get("is_auction", False),
                "new_building": listing.get("new_building", False),
                "owner_direct": listing.get("owner_direct"),
                "gps_lat":      listing.get("gps_lat"),
                "gps_lon":      listing.get("gps_lon"),
                **listing,
            },
        )
        # price_history — len ak bol listing skutočne nový
        if result:
            _execute(
                con,
                "INSERT INTO price_history (id, source, price, recorded_at) VALUES (%s, %s, %s, %s)",
                (listing["id"], listing["source"], listing["price"], now),
            )


def get_listings_by_locality(locality: str, source: str | None = None) -> list[dict]:
    """Vráti inzeráty pre danú lokalitu (pre výpočet priemeru)."""
    with _conn() as con:
        if source:
            return _fetchall(
                con,
                "SELECT * FROM listings WHERE locality = %s AND source = %s AND price > 0",
                (locality, source),
            )
        else:
            return _fetchall(
                con,
                "SELECT * FROM listings WHERE locality = %s AND price > 0",
                (locality,),
            )


# ── Seen IDs ──────────────────────────────────────────────────

def is_new(listing_id: str, source: str) -> bool:
    """True ak tento inzerát sme ešte nevideli."""
    with _conn() as con:
        row = _fetchone(
            con,
            "SELECT 1 FROM seen_ids WHERE id = %s AND source = %s",
            (listing_id, source),
        )
    return row is None


def mark_seen(listing_id: str, source: str) -> None:
    """Označ inzerát ako videný."""
    with _conn() as con:
        _execute(
            con,
            "INSERT INTO seen_ids (id, source, first_seen) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (listing_id, source, datetime.now().isoformat()),
        )


def bootstrap_seen(listings: list[dict]) -> None:
    """Pri prvom spustení označ všetky existujúce inzeráty ako videné
    bez posielania alertov — zabraňuje flood pri štarte.
    Zároveň ich označ aj v free_sent, aby bootstrap inzeráty
    nešli do Free kanála s oneskorením.
    """
    now = datetime.now().isoformat()
    with _conn() as con:
        _executemany(
            con,
            "INSERT INTO seen_ids (id, source, first_seen) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            [(l["id"], l["source"], now) for l in listings],
        )
        _executemany(
            con,
            "INSERT INTO free_sent (id, source, sent_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            [(l["id"], l["source"], now) for l in listings],
        )


# ── Free kanál ────────────────────────────────────────────────

def get_pending_free_alerts(delay_hours: int = 24) -> list[dict]:
    """Vráti inzeráty ktoré:
    - boli prvýkrát videné pred viac ako delay_hours hodinami
    - ešte neboli poslané do Free kanála
    """
    with _conn() as con:
        return _fetchall(
            con,
            """
            SELECT l.*, s.first_seen
            FROM listings l
            JOIN seen_ids s ON l.id = s.id AND l.source = s.source
            LEFT JOIN free_sent f ON l.id = f.id AND l.source = f.source
            WHERE f.id IS NULL
              AND s.first_seen::timestamp <= NOW() - (%s * INTERVAL '1 hour')
            ORDER BY s.first_seen ASC
            """,
            (delay_hours,),
        )


def mark_free_sent(listing_id: str, source: str) -> None:
    """Označ inzerát ako odoslaný do Free kanála."""
    with _conn() as con:
        _execute(
            con,
            "INSERT INTO free_sent (id, source, sent_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (listing_id, source, datetime.now().isoformat()),
        )

# ── Free today count ──────────────────────────────────────────

def get_free_sent_today_count() -> int:
    """Koľko free alertov sme dnes už poslali."""
    with _conn() as con:
        return _fetchscalar(
            con,
            "SELECT COUNT(*) FROM free_sent WHERE sent_at::date = CURRENT_DATE",
        ) or 0

# ── Stats ─────────────────────────────────────────────────────

def stats() -> dict:
    """Základné štatistiky — užitočné pri debugovaní."""
    with _conn() as con:
        total    = _fetchscalar(con, "SELECT COUNT(*) FROM listings")
        seen     = _fetchscalar(con, "SELECT COUNT(*) FROM seen_ids")
        free_out = _fetchscalar(con, "SELECT COUNT(*) FROM free_sent")
        sources  = _fetchall(con, "SELECT source, COUNT(*) as n FROM listings GROUP BY source")
    return {
        "total_listings": total or 0,
        "total_seen":     seen or 0,
        "free_sent":      free_out or 0,
        "by_source":      {r["source"]: r["n"] for r in sources},
    }


# ── Weekly Stats ──────────────────────────────────────────────

def get_weekly_deals() -> list[dict]:
    """Vráti inzeráty z posledných 7 dní kde deal_score >= 10%."""
    with _conn() as con:
        rows = _fetchall(
            con,
            """
            SELECT l.source, l.title, l.price, l.area_m2, l.locality, l.url, l.district, l.rooms
            FROM listings l
            JOIN seen_ids s ON l.id = s.id AND l.source = s.source
            WHERE s.first_seen::timestamp >= NOW() - INTERVAL '7 days'
              AND l.price > 0
              AND l.area_m2 > 0
            ORDER BY s.first_seen DESC
            """,
        )

    deals = []
    for row in rows:
        listing = {
            "source":   row["source"],
            "title":    row["title"],
            "price":    row["price"],
            "area_m2":  row["area_m2"],
            "locality": row["locality"],
            "url":      row["url"],
            "district": row["district"],
            "rooms":    row["rooms"],
        }
        try:
            from processing import deal_score as ds
            sc = ds.score(listing)
            if sc and sc["pct_below"] >= 10:
                listing["pct_below"] = sc["pct_below"]
                deals.append(listing)
        except Exception:
            pass

    return deals
