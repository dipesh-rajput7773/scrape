"""
24/7 Continuous Lead Engine
Runs forever — scrapes all sources, enriches, scores, stores in DB.
Never collects duplicate leads. Rotates through all niches and locations.

Usage:
    python continuous_runner.py                      # run forever
    python continuous_runner.py --once               # run one cycle and stop
    python continuous_runner.py --niche realestate   # only one niche
    python continuous_runner.py --interval 120       # 120 min between cycles

Press Ctrl+C to stop gracefully.
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime

# ── Schedule config ───────────────────────────────────────────────────────────
# Each entry: (niche, location, sources_list)
# Rotates through these in order, repeating forever

SCHEDULE = [
    # Dubai — high ticket
    ("realestate", "Dubai",      ["maps", "reddit"]),
    ("gym",        "Dubai",      ["maps"]),
    ("salon",      "Dubai",      ["maps"]),
    # London — high ticket
    ("realestate", "London",     ["maps", "reddit"]),
    ("dental",     "London",     ["maps"]),
    ("gym",        "London",     ["maps"]),
    # New York
    ("realestate", "New York",   ["maps", "reddit"]),
    ("dental",     "New York",   ["maps"]),
    ("it",         "New York",   ["maps", "reddit"]),
    # Miami
    ("realestate", "Miami",      ["maps"]),
    ("gym",        "Miami",      ["maps"]),
    # Morocco (Casablanca)
    ("realestate", "Casablanca", ["maps"]),
    ("salon",      "Casablanca", ["maps"]),
    ("dental",     "Casablanca", ["maps"]),
    # Morocco (Marrakech)
    ("realestate", "Marrakech",  ["maps"]),
    ("salon",      "Marrakech",  ["maps"]),
    # Abu Dhabi
    ("realestate", "Abu Dhabi",  ["maps"]),
    # Reddit — global inbound (no location needed)
    ("general",    "",           ["reddit"]),
    ("realestate", "",           ["reddit"]),
    ("dental",     "",           ["reddit"]),
    ("gym",        "",           ["reddit"]),
    ("it",         "",           ["reddit"]),
    ("ecom",       "",           ["reddit"]),
]

LEADS_PER_SOURCE = 50   # per keyword per source per run
LOG_FILE = "runner.log"


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_cmd(cmd: list[str], timeout: int = 600) -> bool:
    log(f"$ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=timeout)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"[!] Timeout after {timeout}s")
        return False
    except Exception as e:
        log(f"[!] Error: {e}")
        return False


def import_to_db(csv_path: str, niche: str, location: str, source: str) -> int:
    """Import a CSV into the leads DB, return count of new leads added."""
    if not os.path.exists(csv_path):
        return 0
    try:
        from leads_db import LeadsDB
        db = LeadsDB()
        added, skipped = db.import_csv(csv_path, niche=niche, location=location, source=source)
        log(f"  DB import: +{added} new, {skipped} duplicates skipped")
        return added
    except Exception as e:
        log(f"  [!] DB import error: {e}")
        return 0


def merge_csvs(files: list[str], out: str) -> int:
    merged, seen, keys = [], set(), None
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not keys:
                keys = reader.fieldnames
            for row in reader:
                k = (
                    (row.get("business_name") or row.get("name") or "")
                    + (row.get("phone") or row.get("email") or row.get("reddit_url") or "")
                ).lower().strip()
                if k and k not in seen:
                    seen.add(k)
                    merged.append(row)
    if merged and keys:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(merged)
    return len(merged)


# ── One cycle ─────────────────────────────────────────────────────────────────

def run_cycle(niche: str, location: str, sources: list[str],
              py: str, cycle_id: str) -> int:
    tag = f"{niche}_{location.replace(' ','_').lower()}_{cycle_id}" if location else f"{niche}_{cycle_id}"
    log(f"\n--- Cycle: {niche.upper()} / {location or 'global'} / {sources} ---")

    all_files = []

    # ── Scrape ────────────────────────────────────────────────────────────────
    if "maps" in sources and location:
        from run_pipeline import NICHE_KEYWORDS
        keywords = NICHE_KEYWORDS.get(niche, [niche])
        for kw in keywords:
            out = f"tmp_{tag}_{kw.replace(' ','_')}.csv"
            run_cmd([py, "maps_scraper.py", kw, location,
                     "--max", str(LEADS_PER_SOURCE), "--out", out], timeout=300)
            all_files.append(out)

    if "reddit" in sources:
        out = f"tmp_{tag}_reddit.csv"
        run_cmd([py, "reddit_scraper.py", "--niche", niche,
                 "--max", str(LEADS_PER_SOURCE * 2), "--out", out], timeout=120)
        all_files.append(out)

    if "instagram" in sources and location:
        from run_pipeline import NICHE_IG_HASHTAGS
        hashtags = NICHE_IG_HASHTAGS.get(niche, [niche])
        loc_slug = location.lower().replace(" ", "")
        tags_str = ",".join(hashtags + [f"{h}{loc_slug}" for h in hashtags[:2]])
        out = f"tmp_{tag}_ig.csv"
        run_cmd([py, "instagram_scraper.py", "--hashtags", tags_str,
                 "--max", str(LEADS_PER_SOURCE), "--out", out,
                 "--user", os.getenv("IG_USER",""), "--pass", os.getenv("IG_PASS","")],
                timeout=300)
        all_files.append(out)

    # ── Merge all scraped files ───────────────────────────────────────────────
    existing_files = [f for f in all_files if os.path.exists(f)]
    if not existing_files:
        log("  No data collected this cycle")
        return 0

    leads_file    = f"tmp_{tag}_leads.csv"
    enriched_file = f"tmp_{tag}_enriched.csv"
    total = merge_csvs(existing_files, leads_file)
    log(f"  Merged: {total} raw leads")

    if total == 0:
        _cleanup(all_files + [leads_file])
        return 0

    # ── Enrich ───────────────────────────────────────────────────────────────
    run_cmd([py, "enrich.py", leads_file, enriched_file], timeout=600)

    # ── Import to DB (deduplication happens here) ─────────────────────────────
    source_str = "+".join(sources)
    new_leads = import_to_db(enriched_file, niche, location, source_str)

    # ── Cleanup temp files ────────────────────────────────────────────────────
    _cleanup(all_files + [leads_file, enriched_file])

    log(f"  Result: {new_leads} NEW leads added to DB")
    return new_leads


def _cleanup(files: list[str]):
    for f in files:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once",     action="store_true", help="Run one full cycle and exit")
    ap.add_argument("--niche",    default=None,        help="Only run this niche")
    ap.add_argument("--interval", type=int, default=60, help="Minutes between full cycles (default 60)")
    args = ap.parse_args()

    py = sys.executable

    # Filter schedule if niche specified
    schedule = SCHEDULE
    if args.niche:
        schedule = [(n, l, s) for n, l, s in SCHEDULE if n == args.niche]
        if not schedule:
            print(f"[!] No schedule entries for niche: {args.niche}")
            sys.exit(1)

    log(f"=== Qorvai 24/7 Lead Engine Started ===")
    log(f"Schedule entries: {len(schedule)} | Interval: {args.interval} min")
    log(f"Leads per source: {LEADS_PER_SOURCE} | DB: leads.db")

    cycle_num = 0
    while True:
        cycle_start = time.time()
        cycle_num  += 1
        total_new   = 0

        log(f"\n{'='*60}")
        log(f"CYCLE #{cycle_num} START")
        log(f"{'='*60}")

        for niche, location, sources in schedule:
            try:
                cycle_id = f"c{cycle_num}"
                new = run_cycle(niche, location, sources, py, cycle_id)
                total_new += new
            except KeyboardInterrupt:
                log("Stopped by user.")
                sys.exit(0)
            except Exception as e:
                log(f"[!] Cycle error: {e}")
                continue

        # Print DB stats after each full cycle
        try:
            from leads_db import LeadsDB
            s = LeadsDB().stats()
            log(f"\n=== DB STATS after cycle #{cycle_num} ===")
            log(f"  Total: {s['total']} | Hot: {s['hot']} | Warm: {s['warm']} | "
                f"Cold: {s['cold']} | New this cycle: {total_new}")
            log(f"  Has email: {s['with_email']} | Has phone: {s['with_phone']}")
        except Exception:
            pass

        if args.once:
            log("--once flag set. Stopping.")
            break

        elapsed = (time.time() - cycle_start) / 60
        wait    = max(0, args.interval - elapsed)
        log(f"\nCycle #{cycle_num} done in {elapsed:.1f} min. "
            f"Waiting {wait:.0f} min before next cycle...")

        try:
            time.sleep(wait * 60)
        except KeyboardInterrupt:
            log("Stopped by user.")
            break


if __name__ == "__main__":
    main()
