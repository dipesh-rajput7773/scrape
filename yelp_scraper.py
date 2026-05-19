from __future__ import annotations
"""
Yelp Business Scraper — Anti-ban, stealth Playwright.
Backup source when Google Maps blocks or returns thin results.

Yelp has weaker anti-scraping than Google + structured data.
Gets: business name, phone, website, address, rating, review count, category.

Usage:
    python yelp_scraper.py "dentist" "Dubai" --max 50 --out yelp_leads.csv
"""

import argparse
import asyncio
import csv
import random
import re
import sys
import os

from playwright.async_api import async_playwright

from stealth import (
    create_stealth_context, patch_page, human_scroll,
    random_delay, get_proxy, random_ua, random_viewport,
)


YELP_SEARCH = "https://www.yelp.com/search?find_desc={query}&find_loc={location}&start={offset}"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{7,}\d)")
JUNK_EMAILS = (".png", ".jpg", ".svg", "example.com", "sentry", "wix.com", "yelp.com")


def _clean_email(e: str) -> str | None:
    e = e.lower().strip()
    if any(j in e for j in JUNK_EMAILS):
        return None
    if len(e) > 6 and "@" in e and "." in e.split("@")[1]:
        return e
    return None


async def _extract_business_detail(page, url: str) -> dict:
    """Open a Yelp business page and extract contact info."""
    result = {"website": "", "phone": "", "email": ""}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await random_delay(1.5, 3.0)

        data = await page.evaluate("""() => {
            // Phone
            let phone = '';
            document.querySelectorAll('p').forEach(p => {
                if (p.innerText.match(/^[+\\d][\\d\\s\\-().]{6,}/)) phone = p.innerText.trim();
            });
            const phoneSel = document.querySelector('a[href^="tel:"]');
            if (phoneSel) phone = phoneSel.innerText.trim() || phoneSel.href.replace('tel:', '');

            // Website link
            let website = '';
            document.querySelectorAll('a[href]').forEach(a => {
                const txt = (a.innerText || '').toLowerCase();
                const href = a.href || '';
                if ((txt.includes('website') || txt.includes('business website'))
                    && !href.includes('yelp.com')) {
                    website = href;
                }
            });
            // Fallback: biz_website attribute
            const bw = document.querySelector('[data-testid="biz-website"] a, a.css-1um3nx');
            if (bw && !website) website = bw.href || '';

            return { phone, website };
        }""")

        result["phone"]   = data.get("phone", "")
        result["website"] = data.get("website", "")

        # Try to extract email from the business website (not Yelp itself)
        website = result["website"]
        if website and website.startswith("http") and "yelp.com" not in website:
            try:
                await page.goto(website, wait_until="domcontentloaded", timeout=15000)
                await random_delay(1.0, 2.0)
                html = await page.content()
                emails = [_clean_email(e) for e in EMAIL_RE.findall(html)]
                emails = [e for e in emails if e]
                if not emails:
                    # Try /contact page
                    contact_url = website.rstrip("/") + "/contact"
                    await page.goto(contact_url, wait_until="domcontentloaded", timeout=10000)
                    html2 = await page.content()
                    emails = [_clean_email(e) for e in EMAIL_RE.findall(html2)]
                    emails = [e for e in emails if e]
                if emails:
                    result["email"] = emails[0]
            except Exception:
                pass

    except Exception as e:
        print(f"  [!] Detail error: {str(e)[:60]}")

    return result


async def scrape_yelp(query: str, location: str, max_results: int, headless: bool) -> list[dict]:
    results = []
    seen = set()
    offset = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx = await create_stealth_context(browser, viewport=random_viewport(), ua=random_ua())
        page = await ctx.new_page()
        await patch_page(page)

        while len(results) < max_results:
            url = YELP_SEARCH.format(
                query=query.replace(" ", "+"),
                location=location.replace(" ", "+"),
                offset=offset,
            )
            print(f"[*] Yelp page offset={offset}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            except Exception as e:
                print(f"[!] Page load failed: {e}")
                break

            await random_delay(2.0, 4.0)

            # Check for CAPTCHA / block
            content = await page.content()
            if "captcha" in content.lower() or "robot" in content.lower():
                print("[!] CAPTCHA detected on Yelp. Stopping.")
                break

            # Extract listing cards
            cards = await page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('[data-testid="serp-ia-card"]').forEach(card => {
                    const nameEl = card.querySelector('a.css-19v1rkv, h3 a, [class*="businessName"] a');
                    const name   = nameEl ? nameEl.innerText.trim() : '';
                    const href   = nameEl ? (nameEl.href || '') : '';

                    const ratingEl = card.querySelector('[aria-label*="star rating"], .i-stars');
                    const rating   = ratingEl
                        ? (ratingEl.getAttribute('aria-label') || '').replace(' star rating','').trim()
                        : '';

                    const reviewEl = card.querySelector('span[class*="reviewCount"], .reviewCount');
                    const reviews  = reviewEl ? reviewEl.innerText.replace(/[()]/g,'').trim() : '';

                    const addrEl  = card.querySelector('address, p[class*="secondaryAttributes"]');
                    const address = addrEl ? addrEl.innerText.trim() : '';

                    if (name && href.includes('/biz/')) {
                        results.push({ name, href, rating, reviews, address });
                    }
                });
                return results;
            }""")

            if not cards:
                print("[!] No cards found on this page. Yelp layout may have changed.")
                break

            print(f"[*] Found {len(cards)} listings on this page")

            for card in cards:
                if len(results) >= max_results:
                    break
                name = card.get("name", "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())

                biz_url = card.get("href", "")
                if not biz_url.startswith("http"):
                    biz_url = "https://www.yelp.com" + biz_url

                print(f"  [{len(results)+1}] {name[:50]} — visiting detail page...")
                detail = await _extract_business_detail(page, biz_url)
                await random_delay(2.0, 4.5)

                row = {
                    "business_name": name,
                    "phone":         detail.get("phone", ""),
                    "website":       detail.get("website", ""),
                    "cta_url":       detail.get("website", ""),
                    "email":         detail.get("email", ""),
                    "address":       card.get("address", ""),
                    "rating":        card.get("rating", ""),
                    "reviews":       card.get("reviews", ""),
                    "has_website":   "yes" if detail.get("website") else "no",
                    "source":        "yelp",
                    "yelp_url":      biz_url,
                }
                results.append(row)
                print(
                    f"     phone={'[OK]' if row['phone'] else '[X]'} "
                    f"web={'[OK]' if row['website'] else '[X]'} "
                    f"email={'[OK]' if row['email'] else '[X]'}"
                )

            if len(cards) < 10:
                print("[*] Less than 10 results — probably last page.")
                break

            offset += 10
            await human_scroll(page, distance=random.randint(400, 900))
            await random_delay(2.0, 4.0)

        await browser.close()

    print(f"\n[OK] Yelp: {len(results)} businesses scraped")
    return results


def save_csv(rows: list, path: str):
    if not rows:
        print("[!] No results to save")
        return
    keys = ["business_name", "phone", "website", "email", "address",
            "rating", "reviews", "has_website", "source", "yelp_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] Saved {len(rows)} -> {path}")


def main():
    ap = argparse.ArgumentParser(description="Yelp business scraper")
    ap.add_argument("query",    help='Niche e.g. "dentist"')
    ap.add_argument("location", help='City e.g. "Dubai"')
    ap.add_argument("--max",  type=int, default=50, help="Max results")
    ap.add_argument("--out",  default="yelp_leads.csv")
    ap.add_argument("--show", action="store_true", help="Show browser")
    args = ap.parse_args()

    rows = asyncio.run(scrape_yelp(args.query, args.location, args.max, headless=not args.show))
    save_csv(rows, args.out)


if __name__ == "__main__":
    main()
