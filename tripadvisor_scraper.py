"""
TripAdvisor Scraper — Restaurants, Hotels, Tourism businesses.

TripAdvisor lists millions of hospitality businesses globally.
Gets: name, rating, reviews, cuisine, phone, address, website → email.

Usage:
    python tripadvisor_scraper.py restaurant "Dubai" --max 50
    python tripadvisor_scraper.py hotel "Toronto" --max 30
"""

import argparse
import asyncio
import re
import csv
from urllib.parse import quote_plus

from playwright.async_api import async_playwright
from stealth import create_stealth_context, patch_page, random_delay, get_proxy, random_ua

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
JUNK     = (".png", ".jpg", "example.com", "tripadvisor.com", "noreply", "sentry")

# TripAdvisor geo IDs for major cities (add more as needed)
GEO_IDS = {
    "dubai":       "g295424",
    "toronto":     "g155019",
    "sydney":      "g255060",
    "london":      "g186338",
    "new york":    "g60763",
    "los angeles": "g32655",
    "singapore":   "g294265",
    "mumbai":      "g304554",
    "delhi":       "g304551",
    "paris":       "g187147",
    "amsterdam":   "g188633",
    "bangkok":     "g293916",
}

BASE = "https://www.tripadvisor.com"


def _get_geo(location: str) -> str:
    key = location.lower().strip()
    for city, geo in GEO_IDS.items():
        if city in key:
            return geo
    return ""


def _clean_email(e: str) -> str | None:
    e = e.lower().strip().rstrip(".")
    if any(j in e for j in JUNK):
        return None
    if len(e) > 6 and "@" in e and "." in e.split("@")[1]:
        return e
    return None


async def _extract_contact(page, ta_profile_url: str) -> dict:
    """Visit TripAdvisor business page to get website/phone, then visit site for email."""
    result = {"website": "", "phone": "", "email": ""}
    try:
        await page.goto(ta_profile_url, wait_until="domcontentloaded", timeout=25000)
        await random_delay(1.5, 3.0)

        contact = await page.evaluate("""() => {
            let website = '', phone = '';

            // Website button
            document.querySelectorAll('a[href]').forEach(a => {
                const href = (a.href || '').toLowerCase();
                const txt  = (a.innerText || '').toLowerCase();
                if ((txt.includes('website') || txt.includes('visit site'))
                    && !href.includes('tripadvisor')) {
                    website = a.href;
                }
            });

            // Phone - look for tel: links or phone data
            const tel = document.querySelector('a[href^="tel:"], [data-automation="OVERVIEW_CONTACT_PHONE"]');
            if (tel) phone = tel.innerText.trim() || tel.href.replace('tel:','');

            // Also check the "Contact" section
            document.querySelectorAll('button, a').forEach(el => {
                const txt = (el.innerText || '').toLowerCase();
                if (txt.match(/^[+\\d].*\\d{4}/)) phone = el.innerText.trim();
            });

            return { website, phone };
        }""")

        result["website"] = contact.get("website", "")
        result["phone"]   = contact.get("phone", "")

        # Extract email from their own website
        if result["website"] and result["website"].startswith("http"):
            for path in ["", "/contact", "/contact-us", "/about"]:
                try:
                    await page.goto(result["website"].rstrip("/") + path,
                                    wait_until="domcontentloaded", timeout=12000)
                    await random_delay(0.8, 1.5)
                    html = await page.content()
                    emails = [_clean_email(e) for e in EMAIL_RE.findall(html) if _clean_email(e)]
                    if emails:
                        for e in emails:
                            if any(e.startswith(p) for p in
                                   ("info@","contact@","hello@","reservations@","booking@")):
                                result["email"] = e
                                break
                        if not result["email"]:
                            result["email"] = emails[0]
                        break
                except Exception:
                    pass

    except Exception as ex:
        print(f"  [!] {str(ex)[:60]}")

    return result


async def scrape_tripadvisor(category: str, location: str,
                              max_results: int, headless: bool) -> list[dict]:
    """
    category: 'restaurant' or 'hotel' or 'attraction'
    location: city name
    """
    results = []
    seen    = set()
    geo     = _get_geo(location)

    # Build URL
    cat_map = {
        "restaurant": "Restaurants",
        "restaurants": "Restaurants",
        "hotel":       "Hotels",
        "hotels":      "Hotels",
        "attraction":  "Attractions",
    }
    cat_slug = cat_map.get(category.lower(), "Restaurants")

    if geo:
        list_url = f"{BASE}/{cat_slug}-{geo}-{location.replace(' ','+')}.html"
    else:
        list_url = f"{BASE}/Search?q={quote_plus(location)}&searchSessionId=&geo=&offset=0&searchNearby=false&sid=&blockRedirect=true&search_type=find"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx     = await create_stealth_context(browser, ua=random_ua())
        page    = await ctx.new_page()
        await patch_page(page)

        print(f"[tripadvisor] {list_url}")
        try:
            await page.goto(list_url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"[tripadvisor] Load failed: {e}")
            await browser.close()
            return []

        await random_delay(2.5, 4.0)

        page_num = 0
        while len(results) < max_results:
            listings = await page.evaluate("""() => {
                const items = [];
                // Multiple possible selectors across TA's A/B tested layouts
                const selectors = [
                    '[data-test-target="restaurants-list"] .result-card',
                    'div[data-test="SL_list_item"]',
                    'li[id^="component_"]',
                    '.listing_title a',
                ];
                let cards = [];
                for (const sel of selectors) {
                    const found = document.querySelectorAll(sel);
                    if (found.length > 0) { cards = Array.from(found); break; }
                }

                cards.forEach(card => {
                    const nameEl = card.querySelector(
                        'a.property_title, .listing_title a, '
                        '[data-test="title"] a, h3 a, h2 a, a[href*="/Restaurant_Review"], a[href*="/Hotel_Review"]'
                    );
                    const name = nameEl ? nameEl.innerText.trim() : '';
                    const href = nameEl ? (nameEl.href || '') : '';

                    const ratingEl = card.querySelector(
                        '.ui_bubble_rating, [class*="rating"], svg[aria-label*="bubble"]'
                    );
                    const rating = ratingEl
                        ? (ratingEl.getAttribute('aria-label') || ratingEl.innerText || '').trim()
                        : '';

                    const reviewEl = card.querySelector('[class*="review_count"], [class*="userReviewCount"]');
                    const reviews  = reviewEl ? reviewEl.innerText.replace(/[^0-9,]/g,'') : '';

                    const cuisineEl = card.querySelector(
                        '[class*="cuisine"], [data-test="cuisine-tag"], .cuisines'
                    );
                    const cuisine = cuisineEl ? cuisineEl.innerText.trim() : '';

                    if (name && href.includes('tripadvisor.com')) {
                        items.push({ name, href, rating, reviews, cuisine });
                    }
                });
                return items;
            }""")

            if not listings:
                print(f"[tripadvisor] No listings on page {page_num}")
                break

            print(f"[tripadvisor] Page {page_num}: {len(listings)} found")

            for item in listings:
                if len(results) >= max_results:
                    break

                name = item.get("name", "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())

                profile_url = item.get("href", "")
                print(f"  [{len(results)+1}] {name[:45]}...")
                contact = await _extract_contact(page, profile_url)
                await random_delay(2.0, 4.0)

                row = {
                    "business_name": name,
                    "phone":         contact.get("phone", ""),
                    "website":       contact.get("website", ""),
                    "cta_url":       contact.get("website", ""),
                    "email":         contact.get("email", ""),
                    "address":       location,
                    "rating":        item.get("rating", ""),
                    "reviews":       item.get("reviews", ""),
                    "niche":         item.get("cuisine", category),
                    "source":        "tripadvisor",
                    "tripadvisor_url": profile_url,
                    "has_website":   "yes" if contact.get("website") else "no",
                }
                results.append(row)
                print(
                    f"     phone={'[OK]' if row['phone'] else '[X]'} "
                    f"web={'[OK]' if row['website'] else '[X]'} "
                    f"email={'[OK]' if row['email'] else '[X]'}"
                )

            # Next page
            try:
                nxt = page.locator(
                    'a[aria-label="Next page"], '
                    'a.nav.next, '
                    'span.next.taLnk'
                )
                if await nxt.count() > 0:
                    await nxt.first.click()
                    await random_delay(2.5, 4.0)
                    page_num += 1
                else:
                    break
            except Exception:
                break

        await browser.close()

    print(f"\n[OK] TripAdvisor: {len(results)} businesses scraped")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category", help="restaurant or hotel")
    ap.add_argument("location", help='e.g. "Dubai"')
    ap.add_argument("--max",  type=int, default=50)
    ap.add_argument("--out",  default="tripadvisor_leads.csv")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    rows = asyncio.run(scrape_tripadvisor(args.category, args.location, args.max, not args.show))
    if rows:
        import csv as _csv
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"[OK] Saved {len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
