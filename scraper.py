from __future__ import annotations
﻿"""
Meta Ads Library Scraper
Usage: python scraper.py "ai automation" --country IN --max 100
Output: leads.csv
"""

import asyncio
import argparse
import csv
import re
import sys
from urllib.parse import quote
from playwright.async_api import async_playwright


BASE_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country={country}"
    "&q={query}&search_type=keyword_unordered&media_type=all"
)


async def scrape_ads(query: str, country: str, max_ads: int, headless: bool):
    url = BASE_URL.format(country=country, query=quote(query))
    results = []
    seen_pages = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = await ctx.new_page()

        print(f"[*] Opening: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Dismiss cookie/login banner if present
        try:
            await page.locator("text=Decline optional cookies").first.click(timeout=3000)
        except Exception:
            pass
        try:
            await page.locator("[aria-label='Close']").first.click(timeout=2000)
        except Exception:
            pass

        await page.wait_for_timeout(4000)

        # Scroll until enough ads or no growth
        last_count = 0
        stagnant = 0
        while len(results) < max_ads and stagnant < 4:
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(2500)

            cards = await page.locator("div[role='main'] > div > div > div > div").all()
            if not cards:
                cards = await page.locator("div._7jvw, div._99s5").all()

            # Fallback: grab every card-like block by text patterns
            blocks = await page.evaluate(
                """
                () => {
                  const out = [];
                  const nodes = document.querySelectorAll('div');
                  const seen = new Set();
                  for (const n of nodes) {
                    const t = n.innerText || '';
                    if (t.includes('Library ID') && t.length < 4000) {
                      const key = t.slice(0, 200);
                      if (seen.has(key)) continue;
                      seen.add(key);
                      out.push(t);
                    }
                  }
                  return out;
                }
                """
            )

            for raw in blocks:
                if len(results) >= max_ads:
                    break
                row = parse_block(raw)
                if not row:
                    continue
                key = (row["page_name"], row["library_id"])
                if key in seen_pages:
                    continue
                seen_pages.add(key)
                results.append(row)

            if len(results) == last_count:
                stagnant += 1
            else:
                stagnant = 0
            last_count = len(results)
            print(f"[+] Collected: {len(results)}")

        # Try to enrich with page links by clicking through (optional, slow)
        await browser.close()

    return results


def parse_block(text: str) -> dict | None:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return None

    lib_id = ""
    started = ""
    platforms = ""
    page_name = ""
    ad_copy = ""
    cta_url = ""

    for i, ln in enumerate(lines):
        if ln.startswith("Library ID"):
            m = re.search(r"(\d{6,})", ln)
            if m:
                lib_id = m.group(1)
            elif i + 1 < len(lines):
                lib_id = lines[i + 1]
        if "Started running on" in ln or "Active" in ln and "ago" in ln:
            started = ln
        if "Platforms" in ln and i + 1 < len(lines):
            platforms = lines[i + 1]

    # Page name: usually first non-meta line
    skip_keywords = ("Library ID", "Active", "Platforms", "Started", "Sponsored",
                     "See ad details", "See summary details", "Ad details")
    for ln in lines:
        if any(k in ln for k in skip_keywords):
            continue
        if len(ln) > 1 and len(ln) < 80:
            page_name = ln
            break

    # Ad copy: longest line
    longs = [l for l in lines if len(l) > 40 and not any(k in l for k in skip_keywords)]
    if longs:
        ad_copy = max(longs, key=len)[:500]

    # URL
    m = re.search(r"https?://[^\s)]+", text)
    if m:
        cta_url = m.group(0)

    if not lib_id and not page_name:
        return None

    return {
        "page_name": page_name,
        "library_id": lib_id,
        "started": started,
        "platforms": platforms,
        "ad_copy": ad_copy,
        "cta_url": cta_url,
    }


def save_csv(rows: list[dict], path: str):
    if not rows:
        print("[!] No rows to save")
        return
    keys = ["page_name", "library_id", "started", "platforms", "ad_copy", "cta_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"[[OK]] Saved {len(rows)} ads -> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help='Search keyword e.g. "ai automation"')
    ap.add_argument("--country", default="IN", help="Country code (IN, US, GB...)")
    ap.add_argument("--max", type=int, default=50, help="Max ads to collect")
    ap.add_argument("--out", default="leads.csv", help="Output CSV path")
    ap.add_argument("--show", action="store_true", help="Show browser (non-headless)")
    args = ap.parse_args()

    rows = asyncio.run(
        scrape_ads(args.query, args.country, args.max, headless=not args.show)
    )
    save_csv(rows, args.out)


if __name__ == "__main__":
    main()
