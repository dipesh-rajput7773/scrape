from __future__ import annotations
"""
Healthgrades Scraper — Doctors, Dentists, Clinics, Hospitals.

Healthgrades is the largest US healthcare directory.
Each listing has: name, specialty, phone, address, rating.
We then visit their clinic website to extract email.

Usage:
    python healthgrades_scraper.py dentists "Chicago, IL" --max 50
    python healthgrades_scraper.py doctors  "Houston, TX" --max 30
"""

import argparse
import asyncio
import re
import csv

from playwright.async_api import async_playwright
from stealth import create_stealth_context, patch_page, random_delay, get_proxy, random_ua

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{7,}\d)")
JUNK     = (".png", ".jpg", "example.com", "sentry", "healthgrades.com", "noreply")

BASE = "https://www.healthgrades.com"

# specialty slug → Healthgrades URL segment
SPECIALTY_MAP = {
    "dentists":           "dentists",
    "doctors":            "doctors",
    "physical-therapists":"physical-therapists",
    "hospitals":          "hospitals",
    "dermatologists":     "dermatologists",
    "optometrists":       "optometrists",
    "chiropractors":      "chiropractors",
    "psychiatrists":      "psychiatrists",
    "obstetricians":      "obstetricians-gynecologists",
}


def _clean_email(e: str) -> str | None:
    e = e.lower().strip().rstrip(".")
    if any(j in e for j in JUNK):
        return None
    if len(e) > 6 and "@" in e and "." in e.split("@")[1]:
        return e
    return None


async def _website_email(page, website: str) -> str:
    for path in ["", "/contact", "/contact-us", "/about"]:
        try:
            await page.goto(website.rstrip("/") + path,
                            wait_until="domcontentloaded", timeout=12000)
            await random_delay(0.8, 1.5)
            html  = await page.content()
            emails = [_clean_email(e) for e in EMAIL_RE.findall(html) if _clean_email(e)]
            if emails:
                for e in emails:
                    if any(e.startswith(p) for p in ("info@","contact@","hello@","office@","appointments@")):
                        return e
                return emails[0]
        except Exception:
            pass
    return ""


async def scrape_healthgrades(specialty: str, location: str,
                               max_results: int, headless: bool) -> list[dict]:
    """
    specialty: 'dentists', 'doctors', etc.
    location:  'Chicago, IL' or 'Chicago'
    """
    results = []
    seen    = set()

    # Parse city + state from location
    parts    = [p.strip() for p in location.replace(",", " ").split()]
    city_slug = "-".join(parts).lower()

    # Healthgrades URL patterns
    state_abbr = parts[-1].upper() if len(parts) >= 2 and len(parts[-1]) == 2 else ""
    city_name  = " ".join(parts[:-1]) if state_abbr else location

    specialty_slug = SPECIALTY_MAP.get(specialty.lower(), specialty.lower())

    if state_abbr:
        url = f"{BASE}/{specialty_slug}/{state_abbr.lower()}/{city_name.lower().replace(' ', '-')}"
    else:
        url = f"{BASE}/{specialty_slug}?searchTerm={location.replace(' ', '+')}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx     = await create_stealth_context(browser, ua=random_ua())
        page    = await ctx.new_page()
        await patch_page(page)

        print(f"[healthgrades] {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[healthgrades] Failed to load: {e}")
            await browser.close()
            return []

        await random_delay(2.5, 4.0)

        # Dismiss any modal/popup
        for selector in ['button[aria-label="Close"]', '[data-testid="modal-close"]', '.close-btn']:
            try:
                await page.locator(selector).first.click(timeout=2000)
            except Exception:
                pass

        page_num = 0
        while len(results) < max_results:
            listings = await page.evaluate("""() => {
                const items = [];
                // Try multiple possible selectors (Healthgrades updates layout)
                const cards = document.querySelectorAll(
                    '[data-qa-target="provider-card"], .provider-card, '
                    '.result-card, [class*="ProviderCard"], li.physician-card'
                );
                cards.forEach(card => {
                    const nameEl = card.querySelector(
                        'a[data-qa-target="provider-name"], a.provider-name, '
                        'h2 a, h3 a, [class*="Name"] a'
                    );
                    const name    = nameEl ? nameEl.innerText.trim() : '';
                    const href    = nameEl ? (nameEl.href || '') : '';

                    const ratingEl = card.querySelector('[class*="rating"], [class*="Rating"]');
                    const rating   = ratingEl ? ratingEl.innerText.trim().split('\\n')[0] : '';

                    const phoneEl  = card.querySelector('[class*="phone"], a[href^="tel:"]');
                    const phone    = phoneEl
                        ? (phoneEl.innerText.trim() || phoneEl.href.replace('tel:',''))
                        : '';

                    const addrEl   = card.querySelector('[class*="address"], [class*="Address"]');
                    const address  = addrEl ? addrEl.innerText.trim() : '';

                    const specEl   = card.querySelector('[class*="specialty"], [class*="Specialty"]');
                    const specialty = specEl ? specEl.innerText.trim() : '';

                    if (name) items.push({ name, href, rating, phone, address, specialty });
                });
                return items;
            }""")

            if not listings:
                print(f"[healthgrades] No listings on page {page_num}")
                break

            print(f"[healthgrades] Page {page_num}: {len(listings)} providers")

            for item in listings:
                if len(results) >= max_results:
                    break

                name = item.get("name", "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())

                profile_url = item.get("href", "")
                website = ""
                email   = ""

                # Visit Healthgrades profile to get website
                if profile_url and "healthgrades.com" in profile_url:
                    try:
                        await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
                        await random_delay(1.5, 2.5)

                        profile_data = await page.evaluate("""() => {
                            let website = '', phone = '';
                            // Website link
                            document.querySelectorAll('a[href]').forEach(a => {
                                const txt  = (a.innerText || a.textContent || '').toLowerCase();
                                const href = a.href || '';
                                if ((txt.includes('website') || txt.includes('practice website'))
                                    && !href.includes('healthgrades')) {
                                    website = href;
                                }
                            });
                            // Phone
                            const tel = document.querySelector('a[href^="tel:"]');
                            if (tel) phone = tel.innerText || tel.href.replace('tel:', '');
                            return { website, phone };
                        }""")

                        website = profile_data.get("website", "")
                        if not item.get("phone") and profile_data.get("phone"):
                            item["phone"] = profile_data["phone"]

                        # Get email from their website
                        if website and website.startswith("http"):
                            print(f"  [email] {website[:55]}...")
                            email = await _website_email(page, website)

                    except Exception as ex:
                        print(f"  [!] {str(ex)[:60]}")

                row = {
                    "business_name": name,
                    "phone":         item.get("phone", ""),
                    "website":       website,
                    "cta_url":       website,
                    "email":         email,
                    "address":       item.get("address", ""),
                    "rating":        item.get("rating", ""),
                    "niche":         specialty,
                    "source":        "healthgrades",
                    "has_website":   "yes" if website else "no",
                }
                results.append(row)
                print(
                    f"  [{len(results)}] {name[:45]:<45} "
                    f"phone={'[OK]' if row['phone'] else '[X]'} "
                    f"email={'[OK]' if email else '[X]'}"
                )
                await random_delay(1.5, 3.0)

            # Next page
            try:
                nxt = page.locator('a[aria-label="Next page"], button[aria-label="Next"], a[rel="next"]')
                if await nxt.count() > 0:
                    await nxt.first.click()
                    await random_delay(2.5, 4.0)
                    page_num += 1
                else:
                    break
            except Exception:
                break

        await browser.close()

    print(f"\n[OK] Healthgrades: {len(results)} providers scraped")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specialty", help="e.g. dentists, doctors, physical-therapists")
    ap.add_argument("location",  help='e.g. "Chicago, IL" or "Houston, TX"')
    ap.add_argument("--max",  type=int, default=50)
    ap.add_argument("--out",  default="healthgrades_leads.csv")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    rows = asyncio.run(scrape_healthgrades(args.specialty, args.location, args.max, not args.show))
    if rows:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"[OK] Saved {len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
