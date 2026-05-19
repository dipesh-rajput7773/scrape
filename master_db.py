"""
Master Businesses Database — Qorvai's internal data flywheel.

Every business scraped by ANY user is stored here.
Future searches hit this cache first — no re-scraping needed.
Over time this becomes Qorvai's private Apollo-style database.

Schema: businesses table (separate from leads.db)
"""

import os
import re
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "master_businesses.db")

# Data older than this is considered stale and triggers a re-scrape
FRESH_DAYS = 30


def _norm(name: str, city: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name + city).lower())[:60]


def _safe_int(v) -> int:
    try:
        return int(str(v).replace(",", "").replace("(", "").replace(")", "").strip() or 0)
    except Exception:
        return 0


def _safe_float(v) -> float:
    try:
        return float(str(v).strip() or 0)
    except Exception:
        return 0.0


class MasterDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS businesses (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT NOT NULL,
                    phone         TEXT DEFAULT '',
                    website       TEXT DEFAULT '',
                    address       TEXT DEFAULT '',
                    city          TEXT DEFAULT '',
                    niche         TEXT DEFAULT '',
                    rating        REAL DEFAULT 0,
                    review_count  INTEGER DEFAULT 0,
                    email         TEXT DEFAULT '',
                    email_verified INTEGER DEFAULT 0,
                    instagram     TEXT DEFAULT '',
                    maps_url      TEXT DEFAULT '',
                    source        TEXT DEFAULT 'maps',
                    has_website   INTEGER DEFAULT 0,
                    -- Business health signals
                    has_email     INTEGER DEFAULT 0,
                    has_phone     INTEGER DEFAULT 0,
                    about_text    TEXT DEFAULT '',
                    -- Timestamps
                    last_scraped  REAL DEFAULT 0,
                    last_enriched REAL DEFAULT 0,
                    -- Dedup key: name+city normalized
                    name_city_norm TEXT UNIQUE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_city_niche ON businesses(city, niche)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email     ON businesses(email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rating    ON businesses(rating)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped   ON businesses(last_scraped)")
            conn.commit()

    # ── Cache check ───────────────────────────────────────────────────────

    def is_fresh(self, city: str, niche: str, min_count: int = 10) -> bool:
        """Return True if we have enough fresh data for city+niche."""
        cutoff = time.time() - (FRESH_DAYS * 86400)
        with self._conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM businesses WHERE city=? AND niche=? AND last_scraped>?",
                (city.lower().strip(), niche.lower().strip(), cutoff)
            ).fetchone()[0]
        return count >= min_count

    # ── Query ─────────────────────────────────────────────────────────────

    def query(self, city: str, niche: str, limit: int = 200,
              has_email: bool = False, min_rating: float = 0.0,
              no_website: bool = False, has_phone: bool = False) -> list[dict]:
        """Return cached businesses matching filters."""
        q = "SELECT * FROM businesses WHERE city=? AND niche=?"
        params: list = [city.lower().strip(), niche.lower().strip()]

        if has_email:
            q += " AND email != '' AND email IS NOT NULL"
        if has_phone:
            q += " AND phone != '' AND phone IS NOT NULL"
        if min_rating > 0:
            q += " AND rating >= ?"
            params.append(min_rating)
        if no_website:
            q += " AND has_website = 0"

        q += " ORDER BY last_scraped DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    # ── Write ─────────────────────────────────────────────────────────────

    def upsert(self, row: dict, niche: str = "", city: str = "") -> bool:
        """
        Insert or update a business record.
        Returns True if it was a new insert, False if updated.
        Never overwrites existing data with empty values.
        """
        name = (row.get("business_name") or row.get("name") or "").strip()
        if not name:
            return False

        city_val  = (city  or row.get("city",  "") or "").strip()
        niche_val = (niche or row.get("niche", "") or "").strip()
        norm_key  = _norm(name, city_val)
        if not norm_key:
            return False

        phone   = (row.get("phone",    "") or "").strip()
        website = (row.get("website",  "") or row.get("cta_url", "") or "").strip()
        email   = (row.get("email",    "") or "").strip()
        address = (row.get("address",  "") or "").strip()
        ig      = (row.get("instagram","") or "").strip()
        maps_u  = (row.get("maps_url", "") or "").strip()
        source  = (row.get("source",   "maps")).strip()
        rating  = _safe_float(row.get("rating", 0))
        reviews = _safe_int(row.get("reviews") or row.get("review_count") or 0)
        now     = time.time()

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, phone, email, website FROM businesses WHERE name_city_norm=?",
                (norm_key,)
            ).fetchone()

            if existing:
                # Only overwrite fields that were empty before
                conn.execute("""
                    UPDATE businesses SET
                        phone    = CASE WHEN phone    = '' THEN ? ELSE phone    END,
                        email    = CASE WHEN email    = '' THEN ? ELSE email    END,
                        website  = CASE WHEN website  = '' THEN ? ELSE website  END,
                        rating   = CASE WHEN rating   = 0  THEN ? ELSE rating   END,
                        has_email   = CASE WHEN ? != '' THEN 1 ELSE has_email   END,
                        has_phone   = CASE WHEN ? != '' THEN 1 ELSE has_phone   END,
                        has_website = CASE WHEN ? != '' THEN 1 ELSE has_website END,
                        last_scraped = ?
                    WHERE name_city_norm = ?
                """, (phone, email, website, rating, email, phone, website, now, norm_key))
                conn.commit()
                return False
            else:
                conn.execute("""
                    INSERT INTO businesses
                        (business_name, phone, website, address, city, niche,
                         rating, review_count, email, instagram, maps_url,
                         source, has_website, has_email, has_phone,
                         last_scraped, name_city_norm)
                    VALUES (?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?)
                """, (
                    name, phone, website, address,
                    city_val.lower(), niche_val.lower(),
                    rating, reviews, email, ig, maps_u,
                    source,
                    1 if website else 0,
                    1 if email   else 0,
                    1 if phone   else 0,
                    now, norm_key,
                ))
                conn.commit()
                return True

    def bulk_upsert(self, rows: list[dict], niche: str = "", city: str = "") -> tuple[int, int]:
        """Insert/update many businesses. Returns (new, updated) counts."""
        new, updated = 0, 0
        for row in rows:
            if self.upsert(row, niche=niche, city=city):
                new += 1
            else:
                updated += 1
        return new, updated

    def update_enrichment(self, name_city_norm: str, email: str = "",
                          instagram: str = "", about_text: str = ""):
        """Called after enrich.py runs — updates email/ig/about fields."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE businesses SET
                    email       = CASE WHEN email     = '' THEN ? ELSE email     END,
                    instagram   = CASE WHEN instagram = '' THEN ? ELSE instagram END,
                    about_text  = CASE WHEN about_text= '' THEN ? ELSE about_text END,
                    has_email   = CASE WHEN ? != '' THEN 1 ELSE has_email END,
                    last_enriched = ?
                WHERE name_city_norm = ?
            """, (email, instagram, about_text, email, time.time(), name_city_norm))
            conn.commit()

    # ── Stats ─────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._conn() as conn:
            total      = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
            with_email = conn.execute("SELECT COUNT(*) FROM businesses WHERE email != ''").fetchone()[0]
            with_phone = conn.execute("SELECT COUNT(*) FROM businesses WHERE phone != ''").fetchone()[0]
            cities     = conn.execute("SELECT COUNT(DISTINCT city)  FROM businesses").fetchone()[0]
            niches     = conn.execute("SELECT COUNT(DISTINCT niche) FROM businesses").fetchone()[0]
        return {
            "total": total, "with_email": with_email,
            "with_phone": with_phone, "cities": cities, "niches": niches,
        }

    def coverage(self) -> list[dict]:
        """Show what city+niche combinations we have cached."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    city, niche,
                    COUNT(*)  AS count,
                    SUM(has_email)  AS with_email,
                    SUM(has_phone)  AS with_phone,
                    ROUND(AVG(rating), 1) AS avg_rating,
                    datetime(MAX(last_scraped), 'unixepoch') AS last_scraped
                FROM businesses
                GROUP BY city, niche
                ORDER BY count DESC
            """).fetchall()
            return [dict(r) for r in rows]


# ── Module-level singleton ─────────────────────────────────────────────────
MASTER_DB = MasterDB()
