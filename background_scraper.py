#!/usr/bin/env python3
"""
background_scraper.py — Qorvai Data Flywheel

Runs 24/7 scraping city × niche combos into master_businesses.db.
This is THE moat. Every hour adds ~300-500 businesses.
After 30 days: 200K+ businesses. After 90 days: 1M+

Usage:
    python background_scraper.py              # Run forever
    python background_scraper.py --once       # Single pass (test)
    python background_scraper.py --stats      # Show DB stats
    python background_scraper.py --city Dubai --niche Dentist  # Run one combo
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Global city targets — sorted by population × agency density
CITIES = [
    "Dubai",
    "Toronto",
    "Sydney",
    "London",
    "New York",
    "Mumbai",
    "Singapore",
    "Riyadh",
    "Lagos",
    "Nairobi",
    "Melbourne",
    "Los Angeles",
    "Chicago",
    "Karachi",
    "Cape Town",
    "Lahore",
    "Dhaka",
    "Johannesburg",
    "Bangkok",
    "Manila",
]

# Niches to rotate through — maps to niche_sources.py niche names
NICHES = [
    "Dentist",
    "Gym / Fitness",
    "Salon / Spa",
    "Restaurant",
    "Real Estate Agent",
    "Law Firm",
    "Accounting / CA Firm",
    "Doctor / Clinic",
    "Contractor / Builder",
    "Interior Designer",
    "Auto Repair / Garage",
    "Digital Marketing Agency",
    "Web Design / Dev Agency",
    "AI / Automation Agency",
    "Hotel",
    "Physiotherapist",
    "Tutoring / Education",
    "Recruitment Agency",
]

# Seconds between each niche+city combo (avoids rate limiting)
DELAY_BETWEEN_JOBS = 45

# How many leads to scrape per combo run
LEADS_PER_JOB = 40

# How many days before a combo is considered stale and needs re-scraping
FRESH_DAYS = 30

# Log file
LOG_FILE = os.path.join(PROJECT_DIR, "background_scraper.log")


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Core scrape job ───────────────────────────────────────────────────────────

def run_maps_scrape(niche: str, city: str, max_leads: int = LEADS_PER_JOB) -> list[dict]:
    """Run maps_scraper.py for a niche+city, return parsed rows."""
    tmp_csv = os.path.join(PROJECT_DIR, f"_bg_{niche.replace('/', '_').replace(' ', '_')}_{city.replace(' ', '_')}.csv")

    # Use niche_sources keywords for better results
    try:
        sys.path.insert(0, PROJECT_DIR)
        from niche_sources import get_keywords
        keywords = get_keywords(niche, "maps")
        if not keywords:
            keywords = [niche]
    except Exception:
        keywords = [niche]

    keyword = keywords[0]  # Use primary keyword per run

    cmd = [
        sys.executable,
        os.path.join(PROJECT_DIR, "maps_scraper.py"),
        keyword,
        city,
        "--max", str(max_leads),
        "--out", tmp_csv,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 min max per scrape
        )
        stderr_snippet = result.stderr[-300:] if result.stderr else ""
        if result.returncode != 0 and stderr_snippet:
            log(f"  Scraper stderr: {stderr_snippet.strip()}", "WARN")
    except subprocess.TimeoutExpired:
        log(f"  Timeout scraping {niche} in {city}", "WARN")
        return []
    except Exception as e:
        log(f"  Scraper error: {e}", "ERROR")
        return []

    # Parse CSV output
    rows = []
    if os.path.exists(tmp_csv):
        try:
            with open(tmp_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
        except Exception as e:
            log(f"  CSV parse error: {e}", "WARN")
        finally:
            try:
                os.remove(tmp_csv)
            except Exception:
                pass

    return rows


def store_to_master_db(rows: list[dict], niche: str, city: str) -> tuple[int, int]:
    """Upsert rows into master_businesses.db. Returns (new, updated)."""
    try:
        sys.path.insert(0, PROJECT_DIR)
        from master_db import MasterDB
        db = MasterDB()
        new, updated = db.bulk_upsert(rows, niche=niche.lower(), city=city.lower())
        return new, updated
    except Exception as e:
        log(f"  DB upsert error: {e}", "ERROR")
        return 0, 0


def is_combo_fresh(niche: str, city: str) -> bool:
    """Return True if this niche+city was scraped recently enough to skip."""
    try:
        sys.path.insert(0, PROJECT_DIR)
        from master_db import MasterDB
        db = MasterDB()
        return db.is_fresh(city.lower(), niche.lower(), min_count=10)
    except Exception:
        return False


# ── Job queue ─────────────────────────────────────────────────────────────────

def build_job_queue(skip_fresh: bool = True) -> list[tuple[str, str]]:
    """
    Build prioritized queue of (city, niche) combos to scrape.
    Puts combos with 0 data first, then oldest-scraped.
    """
    jobs = []
    for city in CITIES:
        for niche in NICHES:
            if skip_fresh and is_combo_fresh(niche, city):
                continue
            jobs.append((city, niche))

    log(f"Job queue: {len(jobs)} combos to scrape "
        f"({len(CITIES) * len(NICHES) - len(jobs)} already fresh)")
    return jobs


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_once(city: str = None, niche: str = None, skip_fresh: bool = True):
    """Single pass through all combos (or specific combo)."""
    if city and niche:
        jobs = [(city, niche)]
    else:
        jobs = build_job_queue(skip_fresh=skip_fresh)

    if not jobs:
        log("✅ All combos are fresh. Nothing to scrape. Re-run in 24h.", "INFO")
        return

    total_new = 0
    total_updated = 0

    for i, (city_j, niche_j) in enumerate(jobs, 1):
        log(f"[{i}/{len(jobs)}] Scraping: {niche_j} in {city_j}...")
        rows = run_maps_scrape(niche_j, city_j)

        if rows:
            new, updated = store_to_master_db(rows, niche_j, city_j)
            total_new += new
            total_updated += updated
            log(f"  ✅ {len(rows)} results → +{new} new, {updated} updated in DB")
        else:
            log(f"  ⚠️  0 results (blocked / no data for this combo)", "WARN")

        # Rate limit between jobs
        if i < len(jobs):
            log(f"  💤 Waiting {DELAY_BETWEEN_JOBS}s before next job...")
            time.sleep(DELAY_BETWEEN_JOBS)

    log(f"✅ Pass complete: +{total_new} new businesses, {total_updated} updated | "
        f"Total jobs: {len(jobs)}")
    return total_new, total_updated


def run_forever():
    """Run scraping passes in an infinite loop with a gap between passes."""
    log("🚀 Background scraper started — Qorvai data flywheel is LIVE")
    log(f"   Cities: {len(CITIES)} | Niches: {len(NICHES)} | "
        f"Delay: {DELAY_BETWEEN_JOBS}s/job")

    pass_num = 0
    while True:
        pass_num += 1
        log(f"\n{'='*60}")
        log(f"PASS #{pass_num} STARTED")
        log(f"{'='*60}")

        try:
            result = run_once(skip_fresh=True)
            if result:
                new, updated = result
                log(f"PASS #{pass_num} DONE: +{new} new businesses added to master DB")
        except KeyboardInterrupt:
            log("🛑 Interrupted by user. Stopping.", "INFO")
            break
        except Exception as e:
            log(f"Pass #{pass_num} error: {e}", "ERROR")

        # Between passes: wait 6 hours before cycling again
        gap_hours = 6
        log(f"\n💤 Sleeping {gap_hours}h before next full pass...")
        try:
            time.sleep(gap_hours * 3600)
        except KeyboardInterrupt:
            log("🛑 Interrupted during sleep. Stopping.", "INFO")
            break


def show_stats():
    """Print current master DB stats."""
    try:
        sys.path.insert(0, PROJECT_DIR)
        from master_db import MasterDB
        db = MasterDB()
        s = db.stats()
        cov = db.coverage()

        print("\n" + "="*60)
        print("  QORVAI MASTER DATABASE STATS")
        print("="*60)
        print(f"  Total businesses : {s['total']:,}")
        print(f"  With email       : {s['with_email']:,}  ({round(s['with_email']/max(s['total'],1)*100)}%)")
        print(f"  With phone       : {s['with_phone']:,}  ({round(s['with_phone']/max(s['total'],1)*100)}%)")
        print(f"  Cities covered   : {s['cities']}")
        print(f"  Niches covered   : {s['niches']}")
        print("="*60)

        if cov:
            print("\n  TOP 20 COVERAGE (city × niche):")
            print(f"  {'City':<15} {'Niche':<28} {'Count':>6} {'Emails':>7} {'Last Scraped'}")
            print("  " + "-"*80)
            for row in cov[:20]:
                print(
                    f"  {str(row.get('city','?')).title():<15} "
                    f"{str(row.get('niche','?')).title():<28} "
                    f"{row.get('count',0):>6,} "
                    f"{row.get('with_email',0):>7,} "
                    f"{str(row.get('last_scraped','?'))[:16]}"
                )
        print("="*60 + "\n")
    except Exception as e:
        print(f"Error reading DB: {e}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Qorvai Background Scraper — Data Flywheel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python background_scraper.py               # Run forever (production)
  python background_scraper.py --once        # Single pass, skip fresh combos
  python background_scraper.py --once --force  # Single pass, re-scrape everything
  python background_scraper.py --stats       # Show DB coverage
  python background_scraper.py --city Dubai --niche Dentist  # One combo
        """
    )
    parser.add_argument("--once",   action="store_true", help="Run one pass and exit")
    parser.add_argument("--stats",  action="store_true", help="Show DB stats and exit")
    parser.add_argument("--force",  action="store_true", help="Ignore freshness — re-scrape all")
    parser.add_argument("--city",   type=str, default=None, help="Scrape a specific city")
    parser.add_argument("--niche",  type=str, default=None, help="Scrape a specific niche")
    parser.add_argument("--delay",  type=int, default=DELAY_BETWEEN_JOBS,
                        help=f"Seconds between jobs (default: {DELAY_BETWEEN_JOBS})")
    args = parser.parse_args()

    if args.delay != DELAY_BETWEEN_JOBS:
        DELAY_BETWEEN_JOBS = args.delay

    if args.stats:
        show_stats()
        sys.exit(0)

    if args.once or args.city or args.niche:
        run_once(
            city=args.city,
            niche=args.niche,
            skip_fresh=not args.force,
        )
    else:
        run_forever()
