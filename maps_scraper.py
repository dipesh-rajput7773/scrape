"""
Google Maps Lead Scraper
Usage: python maps_scraper.py "real estate agent" "Dubai" --max 50
Output: maps_leads.csv (business_name, phone, website, address, rating, has_website, cta_url)
"""

import asyncio
import argparse
import csv
import random
import sys
import os
from playwright.async_api import async_playwright

from stealth import (
    create_stealth_context, patch_page, human_scroll, random_delay,
    get_proxy, random_ua, random_viewport,
)


async def scrape_maps(query: str, location: str, max_results: int, headless: bool):
    search = f"{query} in {location}"
    url = "https://www.google.com/maps/search/" + search.replace(" ", "+")
    results = []
    seen = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx = await create_stealth_context(browser, viewport=random_viewport(), ua=random_ua())
        page = await ctx.new_page()
        await patch_page(page)

        print(f"[*] Searching: {search}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await random_delay(2, 4)

        # Accept cookies if prompted
        try:
            await page.locator("text=Accept all").first.click(timeout=3000)
            await random_delay(0.5, 1.5)
        except Exception:
            pass

        stagnant = 0
        last_count = 0

        while len(results) < max_results and stagnant < 6:
            # Grab all listing links from the feed
            links = await page.locator('a[href*="/maps/place/"]').all()

            for link in links:
                if len(results) >= max_results:
                    break
                try:
                    name = await link.get_attribute("aria-label")
                    href = await link.get_attribute("href")
                    if not name or not href:
                        continue
                    key = name.strip().lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    # Click listing to load detail panel
                    await link.click()
                    await random_delay(1.5, 3.0)

                    info = await page.evaluate("""
                        () => {
                            const q = (sel) => {
                                const el = document.querySelector(sel);
                                return el ? el.innerText.trim() : '';
                            };
                            const attr = (sel, a) => {
                                const el = document.querySelector(sel);
                                return el ? (el.getAttribute(a) || '').trim() : '';
                            };

                            // Phone: button with tooltip containing 'phone'
                            let phone = '';
                            document.querySelectorAll('button[data-tooltip]').forEach(btn => {
                                const tip = btn.getAttribute('data-tooltip') || '';
                                if (tip.toLowerCase().includes('phone') || tip.toLowerCase().includes('copy phone')) {
                                    phone = btn.innerText.trim();
                                }
                            });
                            // Fallback: aria-label containing phone
                            if (!phone) {
                                document.querySelectorAll('button[aria-label]').forEach(btn => {
                                    const lbl = btn.getAttribute('aria-label') || '';
                                    if (lbl.match(/^[+\\d][\\d\\s\\-().]{6,}/)) {
                                        phone = lbl.trim();
                                    }
                                });
                            }

                            // Website link
                            let website = '';
                            document.querySelectorAll('a[data-tooltip], a[aria-label]').forEach(a => {
                                const tip = (a.getAttribute('data-tooltip') || a.getAttribute('aria-label') || '').toLowerCase();
                                if (tip.includes('website') || tip.includes('open website')) {
                                    website = a.href || '';
                                }
                            });

                            // Address
                            let address = '';
                            document.querySelectorAll('button[data-tooltip]').forEach(btn => {
                                const tip = btn.getAttribute('data-tooltip') || '';
                                if (tip.toLowerCase().includes('address') || tip.toLowerCase().includes('copy address')) {
                                    address = btn.innerText.trim();
                                }
                            });

                            // Rating
                            const ratingEl = document.querySelector('span.MW4etd') ||
                                             document.querySelector('[aria-label*="stars"]');
                            const rating = ratingEl ? ratingEl.innerText.trim() : '';

                            // Review count
                            const reviewEl = document.querySelector('span.UY7F9') ||
                                             document.querySelector('span[aria-label*="reviews"]');
                            const reviews = reviewEl ? reviewEl.innerText.replace(/[()]/g,'').trim() : '';

                            return { phone, website, address, rating, reviews };
                        }
                    """)

                    website = info.get("website", "")
                    row = {
                        "business_name": name.strip(),
                        "phone":   info.get("phone", ""),
                        "website": website,
                        "cta_url": website,   # enrich.py uses cta_url
                        "address": info.get("address", ""),
                        "rating":  info.get("rating", ""),
                        "reviews": info.get("reviews", ""),
                        "has_website": "yes" if website else "no",
                        "maps_url": href,
                    }
                    results.append(row)
                    print(
                        f"[{len(results)}] {name[:45]:<45} "
                        f"phone={'[OK]' if row['phone'] else '[X]'}  "
                        f"web={'[OK]' if website else '[X]'}"
                    )
                except Exception:
                    continue

            # Human-like scroll
            await human_scroll(page, distance=random.randint(800, 1800), steps=random.randint(3, 6))
            await random_delay(1.5, 3.0)

            if len(results) == last_count:
                stagnant += 1
            else:
                stagnant = 0
            last_count = len(results)

        await browser.close()

    return results


def save_csv(rows: list, path: str):
    if not rows:
        print("[!] No results found")
        return
    keys = ["business_name", "phone", "website", "cta_url", "address",
            "rating", "reviews", "has_website", "maps_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"[[OK]] Saved {len(rows)} businesses -> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query",    help='Business type e.g. "real estate agent"')
    ap.add_argument("location", help='City e.g. "Dubai" or "New York"')
    ap.add_argument("--max",  type=int, default=50,              help="Max results (default 50)")
    ap.add_argument("--out",  default="maps_leads.csv",          help="Output CSV path")
    ap.add_argument("--show", action="store_true",               help="Show browser window")
    args = ap.parse_args()

    rows = asyncio.run(
        scrape_maps(args.query, args.location, args.max, headless=not args.show)
    )
    save_csv(rows, args.out)


if __name__ == "__main__":
    main()
