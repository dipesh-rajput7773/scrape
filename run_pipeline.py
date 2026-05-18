"""
Qorvai Master Pipeline — one command, all sources.

Usage:
  python run_pipeline.py --niche realestate --location "Dubai" --max 100
  python run_pipeline.py --niche gym --location "London" --source all --max 300
  python run_pipeline.py --niche dental --location "New York" --source reddit --max 200 --send

Sources:
  maps      - Google Maps (local businesses, phone + address)
  instagram - Instagram hashtags (business profiles with bio/contact)
  linkedin  - LinkedIn via Google search (professional contacts)
  reddit    - Reddit posts (inbound: people actively looking for automation)
  meta      - Meta Ads Library (businesses running ads)
  ai_news   - AI news from 15+ sources (Anthropic, OpenAI, NVIDIA, Product Hunt, etc.)
  all       - Run all 6 sources in one go

AI News specific:
  python run_pipeline.py --source ai_news --keyword "NVIDIA" --max 50
  python run_pipeline.py --source ai_news --country US --max 100
"""

import argparse
import csv
import os
import subprocess
import sys


# ── Niche config ──────────────────────────────────────────────────────────────

NICHE_KEYWORDS = {
    "realestate": ["real estate agent", "property consultant", "estate agent"],
    "dental":     ["dental clinic", "dentist"],
    "gym":        ["gym", "fitness studio"],
    "salon":      ["beauty salon", "hair salon"],
    "it":         ["IT services", "managed IT"],
    "ecom":       ["online store", "ecommerce store"],
}

NICHE_IG_HASHTAGS = {
    "realestate": ["realestateagent", "propertyagent", "realtorlife"],
    "dental":     ["dentist", "dentalclinic", "dentalcare"],
    "gym":        ["gymowner", "fitnesscoach", "personaltrainer"],
    "salon":      ["salonowner", "hairsalon", "beautycoach"],
    "it":         ["techstartup", "itservices", "saas"],
    "ecom":       ["ecommerce", "shopifystore", "onlinebusiness"],
}

META_COUNTRY = {
    "dubai": "AE", "uae": "AE",
    "london": "GB", "uk": "GB", "manchester": "GB",
    "new york": "US", "usa": "US", "miami": "US", "los angeles": "US",
    "morocco": "MA", "casablanca": "MA",
    "canada": "CA", "toronto": "CA",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_cmd(cmd: list[str]) -> bool:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


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
                # Deduplicate by (name + phone) or (name + email) or URL
                key = (
                    (row.get("business_name") or row.get("name") or "")
                    + (row.get("phone") or row.get("email") or row.get("reddit_url") or "")
                ).lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(row)

    if merged and keys:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(merged)
        print(f"[[OK]] Merged {len(merged)} unique leads -> {out}")
    return len(merged)


# ── Pipeline steps ────────────────────────────────────────────────────────────

def step_maps(py, niche, location, max_n, show, tag) -> list[str]:
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    per_kw   = max(10, max_n // len(keywords))
    files    = []
    show_f   = ["--show"] if show else []
    for kw in keywords:
        out = f"maps_{tag}_{kw.replace(' ','_')}.csv"
        run_cmd([py, "maps_scraper.py", kw, location, "--max", str(per_kw), "--out", out] + show_f)
        files.append(out)
    return files


def step_instagram(py, niche, location, max_n, show, tag, ig_user, ig_pass) -> list[str]:
    hashtags = NICHE_IG_HASHTAGS.get(niche, [niche])
    # Append location to hashtags for more targeted results
    loc_slug = location.lower().replace(" ", "")
    extra    = [f"{h}{loc_slug}" for h in hashtags[:2]]
    all_tags = hashtags + extra
    tags_str = ",".join(all_tags)
    out      = f"instagram_{tag}.csv"
    show_f   = ["--show"] if show else []
    creds    = (["--user", ig_user, "--pass", ig_pass] if ig_user and ig_pass else [])
    run_cmd([py, "instagram_scraper.py", "--hashtags", tags_str,
             "--max", str(max_n), "--out", out] + creds + show_f)
    return [out]


def step_linkedin(py, niche, location, max_n, show, tag) -> list[str]:
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    files    = []
    show_f   = ["--show"] if show else []
    for kw in keywords[:2]:  # top 2 keywords only
        out = f"linkedin_{tag}_{kw.replace(' ','_')}.csv"
        run_cmd([py, "linkedin_scraper.py", kw, location,
                 "--max", str(max_n // 2), "--out", out] + show_f)
        files.append(out)
    return files


def step_reddit(py, niche, max_n, tag) -> list[str]:
    out = f"reddit_{tag}.csv"
    run_cmd([py, "reddit_scraper.py", "--niche", niche,
             "--max", str(max_n), "--out", out])
    return [out]


def step_meta(py, niche, location, max_n, show, tag) -> list[str]:
    country  = META_COUNTRY.get(location.lower(), "US")
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    files    = []
    show_f   = ["--show"] if show else []
    per_kw   = max(10, max_n // len(keywords))
    for kw in keywords:
        out = f"meta_{tag}_{kw.replace(' ','_')}.csv"
        run_cmd([py, "scraper.py", kw, "--country", country,
                 "--max", str(per_kw), "--out", out] + show_f)
        files.append(out)
    return files


def step_ai_news(py, niche, max_n, tag, show) -> list[str]:
    out = f"ai_news_{tag}.csv"
    show_f = ["--show"] if show else []
    run_cmd([py, "ai_news_scraper.py", "--max", str(max_n), "--output", out] + show_f)
    print(f"  -> AI news saved to {out}")
    return [out]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Qorvai Lead Pipeline")
    ap.add_argument("--niche",    default="realestate",
                    choices=["realestate", "dental", "gym", "salon", "it", "ecom", "general"])
    ap.add_argument("--location", default="Dubai",
                    help='Target city e.g. "Dubai", "London", "New York"')
    ap.add_argument("--max",      type=int, default=100,
                    help="Leads per source (default 100)")
    ap.add_argument("--source",   default="maps",
                    choices=["maps", "instagram", "linkedin", "reddit", "meta", "ai_news", "all"],
                    help="Lead source (default: maps)")
    ap.add_argument("--send",     action="store_true",
                    help="Auto-send emails after generating")
    ap.add_argument("--show",     action="store_true",
                    help="Show browser windows")
    ap.add_argument("--ig-user",  default=os.getenv("IG_USER"),  help="Instagram username")
    ap.add_argument("--ig-pass",  default=os.getenv("IG_PASS"),  help="Instagram password")
    args = ap.parse_args()

    py  = sys.executable
    tag = f"{args.niche}_{args.location.replace(' ','_').lower()}"

    all_lead_files = []

    sources = (
        ["maps", "instagram", "linkedin", "reddit", "meta", "ai_news"]
        if args.source == "all"
        else [args.source]
    )

    print(f"\n{'='*55}")
    print(f"  Niche:    {args.niche}")
    print(f"  Location: {args.location}")
    print(f"  Sources:  {', '.join(sources)}")
    print(f"  Max/src:  {args.max}")
    print(f"{'='*55}\n")

    if "maps"      in sources:
        all_lead_files += step_maps(py, args.niche, args.location, args.max, args.show, tag)
    if "instagram" in sources:
        all_lead_files += step_instagram(py, args.niche, args.location, args.max,
                                         args.show, tag, args.ig_user, args.ig_pass)
    if "linkedin"  in sources:
        all_lead_files += step_linkedin(py, args.niche, args.location, args.max, args.show, tag)
    if "reddit"    in sources:
        all_lead_files += step_reddit(py, args.niche, args.max, tag)
    if "meta"      in sources:
        all_lead_files += step_meta(py, args.niche, args.location, args.max, args.show, tag)
    if "ai_news"   in sources:
        all_lead_files += step_ai_news(py, args.niche, args.max, tag, args.show)

    # Merge all sources
    leads_file    = f"leads_{tag}.csv"
    enriched_file = f"enriched_{tag}.csv"
    outreach_file = f"outreach_{tag}.csv"

    total = merge_csvs(all_lead_files, leads_file)
    if total == 0:
        print("[!] No leads collected. Try --show to debug scrapers.")
        sys.exit(1)

    # Enrich (visit websites for email/phone)
    run_cmd([py, "enrich.py", leads_file, enriched_file])

    # Generate cold emails
    run_cmd([py, "cold_email_gen.py", enriched_file, outreach_file, "--niche", args.niche])

    print(f"\n{'='*55}")
    print(f"  DONE!")
    print(f"  Total leads:  {total}")
    print(f"  Leads CSV:    {leads_file}")
    print(f"  Enriched:     {enriched_file}")
    print(f"  Outreach:     {outreach_file}")
    print(f"{'='*55}\n")

    if args.send:
        if not os.getenv("EMAIL_FROM") or not os.getenv("EMAIL_PASS"):
            print("[!] Set EMAIL_FROM and EMAIL_PASS env vars to auto-send")
        else:
            run_cmd([py, "email_sender.py", outreach_file])
    else:
        print(f"Send emails:")
        print(f"  python email_sender.py {outreach_file} --from you@gmail.com --pass 'APP_PASS'")


if __name__ == "__main__":
    main()
