"""
LinkedIn Lead Scraper (via Google Search — no LinkedIn login required)
Finds LinkedIn profiles using Google site: search, then extracts public info.

Usage:
  python linkedin_scraper.py "real estate agent" "Dubai" --max 100
  python linkedin_scraper.py "gym owner" "London" --max 80
  python linkedin_scraper.py "dental clinic owner" "New York" --max 60

Output: linkedin_leads.csv
Columns: name, headline, company, location, linkedin_url, email, cta_url

Volume: ~100-200/run. Use --delay to avoid Google CAPTCHA.
Tip: Run --show first time so you can solve any CAPTCHA manually.
"""

import asyncio
import argparse
import csv
import os
import re
import random
import sys
from playwright.async_api import async_playwright

from stealth import (
    create_stealth_context, patch_page, random_delay, get_proxy,
    random_ua, random_viewport,
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
SLUG_RE  = re.compile(r"linkedin\.com/in/([A-Za-z0-9_\-%.]+)")


def clean_slug(slug: str) -> str:
    slug = slug.split("?")[0].rstrip("/").rstrip("%")
    return slug


async def google_search_linkedin(page, query: str, location: str, start: int) -> list[dict]:
    """Run one Google page and return list of {slug, name, snippet}"""
    search = f'site:linkedin.com/in "{query}" "{location}"'
    url    = f"https://www.google.com/search?q={search.replace(' ', '+')}&start={start}&hl=en"

    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(random.randint(2000, 3500))

    content = await page.content()
    if any(x in content.lower() for x in ["captcha", "unusual traffic", "i'm not a robot"]):
        print("[!] Google CAPTCHA — solve it manually in the browser window, then press Enter")
        input("Press Enter after solving CAPTCHA...")
        content = await page.content()

    rows = []
    seen_slugs = set()

    # Each search result block
    result_blocks = await page.locator("div.g, div[data-hveid]").all()

    for block in result_blocks:
        try:
            block_html = await block.inner_html()
            if "linkedin.com/in/" not in block_html:
                continue

            # Extract LinkedIn slug
            match = SLUG_RE.search(block_html)
            if not match:
                continue
            slug = clean_slug(match.group(1))
            if slug in seen_slugs or len(slug) < 3:
                continue
            seen_slugs.add(slug)

            # Title (name)
            try:
                title = await block.locator("h3").first.inner_text()
                title = title.replace(" | LinkedIn", "").replace("LinkedIn", "").strip()
            except Exception:
                title = slug.replace("-", " ").title()

            # Snippet (headline / summary)
            try:
                snippet = await block.locator("div[data-sncf='1'], span.st, div.VwiC3b").first.inner_text()
            except Exception:
                snippet = ""

            # Try to extract company from snippet
            company = ""
            headline = ""
            if " at " in snippet:
                parts = snippet.split(" at ", 1)
                headline = parts[0].strip()
                company  = parts[1].split("·")[0].strip()
            elif " - " in snippet:
                headline = snippet.split(" - ")[0].strip()

            # Try to find email in snippet
            emails = EMAIL_RE.findall(snippet)

            rows.append({
                "name":         title,
                "headline":     headline or snippet[:120],
                "company":      company,
                "location":     location,
                "linkedin_url": f"https://www.linkedin.com/in/{slug}",
                "email":        emails[0] if emails else "",
                "phone":        "",
                "cta_url":      f"https://www.linkedin.com/in/{slug}",
                "source":       "linkedin",
            })
        except Exception:
            continue

    return rows


async def enrich_profile(page, row: dict) -> dict:
    """Visit LinkedIn public profile to extract extra info (optional, slow)."""
    try:
        await page.goto(row["linkedin_url"], wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(random.randint(1500, 2500))

        data = await page.evaluate("""
            () => {
                const q = (sel) => { const e = document.querySelector(sel); return e ? e.innerText.trim() : ''; };
                const name     = q('h1.text-heading-xlarge, h1');
                const headline = q('.text-body-medium.break-words, .pv-text-details__left-panel .text-body-medium');
                const location = q('.text-body-small.inline.t-black--light.break-words');
                const about    = q('#about ~ div .pv-shared-text-with-see-more span, section.pv-about-section p');
                // Website from contact info section
                const webEl    = document.querySelector('a[href*="http"]:not([href*="linkedin"])');
                const website  = webEl ? webEl.href : '';
                // Email from contact info
                const emailEl  = document.querySelector('a[href^="mailto:"]');
                const email    = emailEl ? emailEl.href.replace('mailto:', '') : '';
                return { name, headline, location, about, website, email };
            }
        """)

        if data.get("name"):   row["name"]     = data["name"]
        if data.get("headline"): row["headline"] = data["headline"][:180]
        if data.get("email"):  row["email"]    = data["email"]
        if data.get("website"):
            row["cta_url"] = data["website"]
        if data.get("about"):
            row["about"]   = data["about"][:300]

    except Exception:
        pass

    return row


async def run(query: str, location: str, max_results: int, enrich: bool, headless: bool, out: str):
    results = []
    seen    = set()
    page_num = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx = await create_stealth_context(browser, viewport=random_viewport(), ua=random_ua())
        page = await ctx.new_page()
        await patch_page(page)

        while len(results) < max_results:
            start = page_num * 10
            print(f"\n[*] Google page {page_num + 1} (results {start + 1}-{start + 10})")

            rows = await google_search_linkedin(page, query, location, start)

            if not rows:
                print("[*] No more Google results")
                break

            for row in rows:
                if len(results) >= max_results:
                    break
                url = row["linkedin_url"]
                if url in seen:
                    continue
                seen.add(url)

                if enrich:
                    row = await enrich_profile(page, row)

                results.append(row)
                print(f"  [{len(results)}] {row['name'][:45]:<45} {row['headline'][:60]}")

            page_num += 1
            # Delay between Google pages to avoid rate limiting
            delay = random.randint(4000, 8000)
            print(f"  waiting {delay // 1000}s before next page...")
            await page.wait_for_timeout(delay)

        await browser.close()

    if not results:
        print("[!] No LinkedIn profiles found. Try --show to debug.")
        return

    # Ensure all rows have same keys
    keys = ["name", "headline", "company", "location", "linkedin_url",
            "email", "phone", "cta_url", "source"]
    if enrich:
        keys.append("about")
    for r in results:
        for k in keys:
            r.setdefault(k, "")

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)
    print(f"\n[[OK]] Saved {len(results)} LinkedIn leads -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query",    help='Job title / role e.g. "real estate agent"')
    ap.add_argument("location", help='Location e.g. "Dubai" or "London"')
    ap.add_argument("--max",    type=int, default=100,           help="Max results (default 100)")
    ap.add_argument("--enrich", action="store_true",             help="Visit each LinkedIn profile for more data (slow)")
    ap.add_argument("--out",    default="linkedin_leads.csv",    help="Output CSV path")
    ap.add_argument("--show",   action="store_true",             help="Show browser (recommended first run)")
    args = ap.parse_args()

    asyncio.run(run(args.query, args.location, args.max, args.enrich, headless=not args.show, out=args.out))


if __name__ == "__main__":
    main()
