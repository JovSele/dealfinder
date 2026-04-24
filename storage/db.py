# storage/db.py — jediné miesto kde sa dotýkame databázy
#
# Tabuľky:
#   listings   — každý inzerát čo sme kedy videli
#   seen_ids   — rýchla množina pre is_new() check
#   free_sent  — inzeráty ktoré už boli poslané do Free kanála

import sqlite3
from contextlib import contextmanager
from datetime import datetime

import config


# ── Schéma ────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id          TEXT NOT NULL,
    source      TEXT NOT NULL,
    title       TEXT,
    price       INTEGER DEFAULT 0,
    area_m2     INTEGER DEFAULT 0,
    locality    TEXT,
    district    TEXT DEFAULT "",
    rooms       INTEGER DEFAULT 0,
    hash        TEXT DEFAULT "",
    url         TEXT,
    scraped_at  TEXT,
    PRIMARY KEY (id, source)
);

CREATE TABLE IF NOT EXISTS seen_ids (
    id          TEXT NOT NULL,
    source      TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    PRIMARY KEY (id, source)
);

CREATE TABLE IF NOT EXISTS free_sent (
    id          TEXT NOT NULL,
    source      TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (id, source)
);

CREATE INDEX IF NOT EXISTS idx_listings_locality
    ON listings(locality, source);
"""


# ── Connection ────────────────────────────────────────────────

@contextmanager
def _conn():
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ── Init ──────────────────────────────────────────────────────

def init():
    """Vytvor tabuľky ak neexistujú. Volaj raz pri štarte."""
    with _conn() as con:
        con.executescript(SCHEMA)


# ── Listings ──────────────────────────────────────────────────

def save_listing(listing: dict) -> None:
    """Ulož inzerát. Ak už existuje (id + source), ignoruj."""
    with _conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO listings
                (id, source, title, price, area_m2, locality, district, rooms, hash, url, scraped_at)
            VALUES
                (:id, :source, :title, :price, :area_m2, :locality, :district, :rooms, :hash, :url, :scraped_at)
            """,
            listing,
        )


def get_listings_by_locality(locality: str, source: str | None = None) -> list[dict]:
    """Vráti inzeráty pre danú lokalitu (pre výpočet priemeru)."""
    with _conn() as con:
        if source:
            rows = con.execute(
                "SELECT * FROM listings WHERE locality = ? AND source = ? AND price > 0",
                (locality, source),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM listings WHERE locality = ? AND price > 0",
                (locality,),
            ).fetchall()
    return [dict(r) for r in rows]


# ── Seen IDs ──────────────────────────────────────────────────

def is_new(listing_id: str, source: str) -> bool:
    """True ak tento inzerát sme ešte nevideli."""
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM seen_ids WHERE id = ? AND source = ?",
            (listing_id, source),
        ).fetchone()
    return row is None


def mark_seen(listing_id: str, source: str) -> None:
    """Označ inzerát ako videný."""
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO seen_ids (id, source, first_seen) VALUES (?, ?, ?)",
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
        con.executemany(
            "INSERT OR IGNORE INTO seen_ids (id, source, first_seen) VALUES (?, ?, ?)",
            [(l["id"], l["source"], now) for l in listings],
        )
        # Bootstrap inzeráty nechceme posielať do free kanála —
        # existovali pred spustením bota
        con.executemany(
            "INSERT OR IGNORE INTO free_sent (id, source, sent_at) VALUES (?, ?, ?)",
            [(l["id"], l["source"], now) for l in listings],
        )


# ── Free kanál ────────────────────────────────────────────────

def get_pending_free_alerts(delay_hours: int = 24) -> list[dict]:
    """Vráti inzeráty ktoré:
    - boli prvýkrát videné pred viac ako delay_hours hodinami
    - ešte neboli poslané do Free kanála

    Tieto pôjdu do DEALFINDER FREE Telegram kanála s ⏰ badge.
    """
    with _conn() as con:
        rows = con.execute(
            """
            SELECT l.*, s.first_seen
            FROM listings l
            JOIN seen_ids s ON l.id = s.id AND l.source = s.source
            LEFT JOIN free_sent f ON l.id = f.id AND l.source = f.source
            WHERE f.id IS NULL
              AND datetime(s.first_seen) <= datetime('now', ? || ' hours')
            ORDER BY s.first_seen ASC
            """,
            (f"-{delay_hours}",),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_free_sent(listing_id: str, source: str) -> None:
    """Označ inzerát ako odoslaný do Free kanála."""
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO free_sent (id, source, sent_at) VALUES (?, ?, ?)",
            (listing_id, source, datetime.now().isoformat()),
        )


# ── Stats ─────────────────────────────────────────────────────

def stats() -> dict:
    """Základné štatistiky — užitočné pri debugovaní."""
    with _conn() as con:
        total    = con.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        seen     = con.execute("SELECT COUNT(*) FROM seen_ids").fetchone()[0]
        free_out = con.execute("SELECT COUNT(*) FROM free_sent").fetchone()[0]
        sources  = con.execute(
            "SELECT source, COUNT(*) as n FROM listings GROUP BY source"
        ).fetchall()
    return {
        "total_listings": total,
        "total_seen":     seen,
        "free_sent":      free_out,
        "by_source":      {r["source"]: r["n"] for r in sources},
    }