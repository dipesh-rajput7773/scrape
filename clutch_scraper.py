from __future__ import annotations
"""
Clutch.co Scraper — IT agencies, marketing firms, design studios.

Clutch lists 100,000+ verified agencies with reviews, ratings, hourly rates.
Each listing has website URL → we visit it for email extraction.

Usage:
    python clutch_scraper.py "digital marketing" --location "Dubai" --max 50
    python clutch_scraper.py "web design" --location "Toronto" --max 30
"""

import argparse
import asyncio
import re
import sys
from urllib.parse import quote_plus

from playwright.async_api import async_playwright
from stealth import create_stealth_context, patch_page, random_delay, get_proxy, random_ua

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
JUNK     = (".png", ".jpg", "example.com", "sentry.io", "noreply", "clutch.co")

BASE = "https://clutch.co"


def _clean_email(e: str) -> str | None:
    e = e.lower().strip().rstrip(".")
    if any(j in e for j in JUNK):
        return None
    if len(e) > 6 and "@" in e and "." in e.split("@")[1]:
        return e
    return None


async def _get_email_from_site(page, website: str) -> str:
    """Visit business website and extract email. Free, no API."""
    for path in ["", "/contact", "/contact-us", "/about", "/about-us"]:
        try:
            url = website.rstrip("/") + path
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await random_delay(0.8, 1.5)
            html = await page.content()
            emails = [_clean_email(e) for e in EMAIL_RE.findall(html)]
            emails = [e for e in emails if e]
            if emails:
                # Prefer business emails over personal
                for e in emails:
                    if any(e.startswith(p) for p in ("info@","contact@","hello@","office@","admin@")):
                        return e
                return emails[0]
        except Exception:
            pass
    return ""


async def scrape_clutch(category: str, location: str, max_results: int, headless: bool) -> list[dict]:
    """
    Scrape Clutch.co for agencies in given category + location.
    category: clutch URL slug e.g. 'digital-marketing', 'web-designers'
    location: city name e.g. 'Dubai', 'Toronto'
    """
    results = []
    seen    = set()
    page_num = 0

    # Build location-aware URL
    # Clutch URL pattern: /agencies/digital-marketing/dubai
    loc_slug = location.lower().replace(" ", "-").replace(",", "")
    list_url = f"{BASE}/agencies/{category}/{loc_slug}"
    fallback_url = f"{BASE}/agencies/{category}?query={quote_plus(location)}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx     = await create_stealth_context(browser, ua=random_ua())
        page    = await ctx.new_page()
        await patch_page(page)

        # Try location-specific URL first, fall back to search
        print(f"[clutch] Trying: {list_url}")
        try:
            await page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(2, 3)
            # If no results, fall back
            count_text = await page.inner_text("body")
            if "no results" in count_text.lower() or "0 providers" in count_text.lower():
                raise Exception("No results for location slug")
        except Exception:
            print(f"[clutch] Falling back to: {fallback_url}")
            try:
                await page.goto(fallback_url, wait_until="domcontentloaded", timeout=30000)
                await random_delay(2, 3)
            except Exception as e:
                print(f"[clutch] Failed to load Clutch: {e}")
                await browser.close()
                return []

        while len(results) < max_results:
            # Extract company cards from listing page
            companies = await page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('.provider-row, li[data-uid], .directory_profile').forEach(card => {
                    // Name
                    const nameEl = card.querySelector(
                        'h3.company_info a, .company_info h3 a, a.company_name, h3 a'
                    );
                    const name = nameEl ? nameEl.innerText.trim() : '';
                    const profileHref = nameEl ? (nameEl.href || '') : '';

                    // Rating
                    const ratingEl = card.querySelector('[class*="rating"] strong, .sg-rating__number');
                    const rating = ratingEl ? ratingEl.innerText.trim() : '';

                    // Review count
                    const reviewEl = card.querySelector('[class*="review"] a, .total-reviews');
                    const reviews = reviewEl ? reviewEl.innerText.replace(/[^0-9]/g,'') : '';

                    // Location
                    const locEl = card.querySelector('[class*="location"], .locality');
                    const location = locEl ? locEl.innerText.trim() : '';

                    // Short description
                    const descEl = card.querySelector('[class*="tagline"], .tagline, p.description');
                    const tagline = descEl ? descEl.innerText.trim().slice(0,200) : '';

                    // Services
                    const serviceEl = card.querySelector('[class*="service"], .services-focus');
                    const services = serviceEl ? serviceEl.innerText.trim().slice(0,100) : '';

                    if (name) items.push({ name, profileHref, rating, reviews, location, tagline, services });
                });
                return items;
            }""")

            if not companies:
                print(f"[clutch] No companies found on page {page_num} — layout may have changed")
                break

            print(f"[clutch] Page {page_num}: {len(companies)} companies found")

            for co in companies:
                if len(results) >= max_results:
                    break

                name = co.get("name", "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())

                profile_url = co.get("profileHref", "")
                if not profile_url.startswith("http"):
                    profile_url = BASE + profile_url

                # Visit Clutch profile to get website
                website = ""
                email   = ""
                phone   = ""
                try:
                    await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
                    await random_delay(1.5, 3.0)

                    contact = await page.evaluate("""() => {
                        // Website link
                        let website = '';
                        document.querySelectorAll('a[href]').forEach(a => {
                            const txt = (a.innerText || '').toLowerCase();
                            const href = a.href || '';
                            if ((txt.includes('visit website') || txt.includes('company website'))
                                && !href.includes('clutch.co')) {
                                website = href;
                            }
                        });
                        // Fallback: any external link in header
                        if (!website) {
                            const el = document.querySelector(
                                'a.website-link, a[data-link-type="website"], .profile-header a[target="_blank"]'
                            );
                            if (el && !el.href.includes('clutch.co')) website = el.href;
                        }

                        // Phone
                        let phone = '';
                        const tel = document.querySelector('a[href^="tel:"]');
                        if (tel) phone = tel.innerText.trim() || tel.href.replace('tel:','');

                        return { website, phone };
                    }""")

                    website = contact.get("website", "")
                    phone   = contact.get("phone", "")

                    # Visit their actual website for email
                    if website and website.startswith("http"):
                        print(f"  [email] Scanning {website[:55]}...")
                        email = await _get_email_from_site(page, website)

                except Exception as ex:
                    print(f"  [!] Profile error: {str(ex)[:60]}")

                row = {
                    "business_name": name,
                    "website":       website,
                    "cta_url":       website,
                    "email":         email,
                    "phone":         phone,
                    "address":       co.get("location", ""),
                    "rating":        co.get("rating", ""),
                    "reviews":       co.get("reviews", ""),
                    "pain_point":    co.get("tagline", ""),
                    "niche":         category,
                    "source":        "clutch",
                    "has_website":   "yes" if website else "no",
                }
                results.append(row)
                print(
                    f"  [{len(results)}] {name[:45]:<45} "
                    f"email={'[OK]' if email else '[X]'} "
                    f"web={'[OK]' if website else '[X]'}"
                )
                await random_delay(1.5, 3.0)

            # Next page
            try:
                next_btn = page.locator('a[rel="next"], a.next, li.next a, [aria-label="Next page"]')
                if await next_btn.count() > 0:
                    await next_btn.first.click()
                    await random_delay(2.5, 4.0)
                    page_num += 1
                else:
                    break
            except Exception:
                break

        await browser.close()

    print(f"\n[OK] Clutch: {len(results)} agencies scraped")
    return results


def main():
    ap = argparse.ArgumentParser(description="Clutch.co agency scraper")
    ap.add_argument("category", help='Clutch category e.g. "digital-marketing"')
    ap.add_argument("--location", default="", help='City e.g. "Dubai"')
    ap.add_argument("--max",  type=int, default=30)
    ap.add_argument("--out",  default="clutch_leads.csv")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    rows = asyncio.run(scrape_clutch(args.category, args.location, args.max, not args.show))

    import csv
    if rows:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"[OK] Saved {len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
