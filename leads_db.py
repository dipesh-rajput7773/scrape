"""
SQLite lead database — global deduplication across ALL runs.
Every lead ever found is stored here. No duplicate is ever processed twice.

Usage (as module):
    from leads_db import LeadsDB
    db = LeadsDB()
    if db.is_new(row):
        db.insert(row)

CLI usage:
    python leads_db.py stats
    python leads_db.py export hot_leads.csv --temp hot
    python leads_db.py import enriched_maps_dubai.csv
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")


def _norm_phone(p: str) -> str:
    return re.sub(r"\D", "", (p or "").split(";")[0])[:12]


def _norm_email(e: str) -> str:
    return (e or "").split(";")[0].strip().lower()


def _norm_name(n: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())[:40]


class LeadsDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT,
                    phone         TEXT,
                    email         TEXT,
                    website       TEXT,
                    address       TEXT,
                    instagram     TEXT,
                    source        TEXT,
                    niche         TEXT,
                    location      TEXT,
                    pain_point    TEXT,
                    score         INTEGER DEFAULT 0,
                    temperature   TEXT DEFAULT 'cold',
                    email_subject TEXT,
                    email_body    TEXT,
                    outreach_sent INTEGER DEFAULT 0,
                    created_at    TEXT DEFAULT (datetime('now')),
                    -- dedup keys
                    phone_norm    TEXT,
                    email_norm    TEXT,
                    name_norm     TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON leads(phone_norm)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email ON leads(email_norm)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_name  ON leads(name_norm)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_temp  ON leads(temperature)")
            conn.commit()

    # ── Deduplication ──────────────────────────────────────────────────────────

    def is_new(self, row: dict) -> bool:
        """Return True if this lead has NOT been seen before."""
        phone = _norm_phone(row.get("phone", ""))
        email = _norm_email(row.get("email", ""))
        name  = _norm_name(row.get("business_name") or row.get("name") or "")

        with self._conn() as conn:
            # Check phone
            if phone and len(phone) >= 7:
                r = conn.execute("SELECT 1 FROM leads WHERE phone_norm=?", (phone,)).fetchone()
                if r:
                    return False
            # Check email
            if email and "@" in email:
                r = conn.execute("SELECT 1 FROM leads WHERE email_norm=?", (email,)).fetchone()
                if r:
                    return False
            # Check business name (only if we have no other match key)
            if not phone and not email and name and len(name) > 4:
                r = conn.execute("SELECT 1 FROM leads WHERE name_norm=?", (name,)).fetchone()
                if r:
                    return False
        return True

    # ── Insert ─────────────────────────────────────────────────────────────────

    def insert(self, row: dict, niche: str = "", location: str = "", source: str = "") -> int | None:
        """Insert a lead. Returns new row id or None if duplicate."""
        if not self.is_new(row):
            return None

        phone = (row.get("phone") or "").split(";")[0].strip()
        email = (row.get("email") or "").split(";")[0].strip()
        name  = row.get("business_name") or row.get("name") or ""

        with self._conn() as conn:
            cur = conn.execute("""
                INSERT OR IGNORE INTO leads
                    (business_name, phone, email, website, address, instagram,
                     source, niche, location,
                     pain_point, score, temperature,
                     email_subject, email_body,
                     phone_norm, email_norm, name_norm)
                VALUES (?,?,?,?,?,?, ?,?,?, ?,?,?, ?,?, ?,?,?)
            """, (
                name,
                phone,
                email,
                row.get("website") or row.get("cta_url") or "",
                row.get("address") or "",
                row.get("instagram") or "",
                source or row.get("source", ""),
                niche  or row.get("niche", ""),
                location or row.get("location") or row.get("address", "")[:60],
                row.get("pain_point") or row.get("post_title") or "",
                int(row.get("score", 0) or 0),
                row.get("temperature", "cold"),
                row.get("email_subject", ""),
                row.get("email_body", ""),
                _norm_phone(phone),
                _norm_email(email),
                _norm_name(name),
            ))
            conn.commit()
            return cur.lastrowid

    def update_score(self, lead_id: int, score: int, temperature: str,
                     pain_point: str, email_subject: str, email_body: str):
        with self._conn() as conn:
            conn.execute("""
                UPDATE leads SET score=?, temperature=?, pain_point=?,
                                 email_subject=?, email_body=?
                WHERE id=?
            """, (score, temperature, pain_point, email_subject, email_body, lead_id))
            conn.commit()

    def mark_sent(self, lead_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE leads SET outreach_sent=1 WHERE id=?", (lead_id,))
            conn.commit()

    # ── Query ──────────────────────────────────────────────────────────────────

    def get_unsent(self, temperature: str = None, min_score: int = 0,
                   has_email: bool = True, limit: int = 200) -> list[dict]:
        q = "SELECT * FROM leads WHERE outreach_sent=0 AND score>=?"
        params = [min_score]
        if temperature:
            q += " AND temperature=?"
            params.append(temperature)
        if has_email:
            q += " AND email != ''"
        q += " ORDER BY score DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self._conn() as conn:
            total   = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            hot     = conn.execute("SELECT COUNT(*) FROM leads WHERE temperature='hot'").fetchone()[0]
            warm    = conn.execute("SELECT COUNT(*) FROM leads WHERE temperature='warm'").fetchone()[0]
            cold    = conn.execute("SELECT COUNT(*) FROM leads WHERE temperature='cold'").fetchone()[0]
            sent    = conn.execute("SELECT COUNT(*) FROM leads WHERE outreach_sent=1").fetchone()[0]
            w_email = conn.execute("SELECT COUNT(*) FROM leads WHERE email!=''").fetchone()[0]
            w_phone = conn.execute("SELECT COUNT(*) FROM leads WHERE phone!=''").fetchone()[0]
        return {
            "total": total, "hot": hot, "warm": warm, "cold": cold,
            "sent": sent, "with_email": w_email, "with_phone": w_phone,
        }

    def export_csv(self, path: str, temperature: str = None, min_score: int = 0):
        rows = self.get_unsent(temperature=temperature, min_score=min_score,
                               has_email=False, limit=10000)
        if not rows:
            print("[!] No leads match filter")
            return
        keys = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print(f"[[OK]] Exported {len(rows)} leads -> {path}")

    def import_csv(self, path: str, niche: str = "", location: str = "", source: str = "") -> tuple[int, int]:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        added, skipped = 0, 0
        for row in rows:
            rid = self.insert(row, niche=niche, location=location, source=source)
            if rid:
                added += 1
            else:
                skipped += 1
        return added, skipped


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Leads database CLI")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("stats")

    exp = sub.add_parser("export")
    exp.add_argument("out_file")
    exp.add_argument("--temp",  default=None, choices=["hot","warm","cold"])
    exp.add_argument("--score", type=int, default=0)

    imp = sub.add_parser("import")
    imp.add_argument("csv_file")
    imp.add_argument("--niche",    default="")
    imp.add_argument("--location", default="")
    imp.add_argument("--source",   default="")

    args = ap.parse_args()
    db = LeadsDB()

    if args.cmd == "stats":
        s = db.stats()
        print(f"\n=== Leads DB ({DB_PATH}) ===")
        print(f"  Total:      {s['total']}")
        print(f"  Hot:        {s['hot']}")
        print(f"  Warm:       {s['warm']}")
        print(f"  Cold:       {s['cold']}")
        print(f"  Sent:       {s['sent']}")
        print(f"  Has email:  {s['with_email']}")
        print(f"  Has phone:  {s['with_phone']}")

    elif args.cmd == "export":
        db.export_csv(args.out_file, temperature=args.temp, min_score=args.score)

    elif args.cmd == "import":
        added, skipped = db.import_csv(args.csv_file, args.niche, args.location, args.source)
        print(f"[[OK]] Imported: {added} new | {skipped} duplicates skipped")

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
