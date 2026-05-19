"""
LinkedIn → Email Extractor

LinkedIn hides emails — direct extraction blocked.
Strategy: Extract company domain from LinkedIn → find email via email_finder pipeline.

Two modes:
  1. Company page  → get website domain → find email
  2. Person profile → get company → get domain → find email

Usage:
    python linkedin_email.py --query "real estate agent Dubai" --max 30
    python linkedin_email.py --url "https://linkedin.com/company/example"
"""

import argparse
import asyncio
import csv
import re
from urllib.parse import quote_plus

from playwright.async_api import async_playwright
from stealth import create_stealth_context, patch_page, random_delay, get_proxy, random_ua
from email_finder import find_email

BASE = "https://www.linkedin.com"


async def _search_companies(page, query: str, location: str, max_results: int) -> list[dict]:
    """Search LinkedIn for companies matching query + location."""
    results = []
    seen    = set()

    search_url = (
        f"{BASE}/search/results/companies/"
        f"?keywords={quote_plus(query + ' ' + location)}"
        f"&origin=GLOBAL_SEARCH_HEADER"
    )

    print(f"[linkedin] Searching: {search_url}")
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(2.5, 4.0)
    except Exception as e:
        print(f"[linkedin] Search failed: {e}")
        return []

    # Handle login wall — LinkedIn often requires login for search
    content = await page.content()
    if "authwall" in content.lower() or "join now" in content.lower() or "sign in" in page.url:
        print("[linkedin] Login wall detected — using public search fallback")
        return await _google_linkedin_search(page, query, location, max_results)

    page_num = 0
    while len(results) < max_results:
        companies = await page.evaluate("""() => {
            const items = [];
            document.querySelectorAll(
                '.search-result__wrapper, li.reusable-search__result-container, '
                '.entity-result'
            ).forEach(card => {
                const nameEl = card.querySelector(
                    '.entity-result__title-text a, .search-result__title a, '
                    'a[data-control-name="search_srp_result"]'
                );
                const name = nameEl ? nameEl.innerText.trim() : '';
                const href = nameEl ? (nameEl.href || '') : '';

                const subtitleEl = card.querySelector(
                    '.entity-result__primary-subtitle, .search-result__truncate'
                );
                const subtitle = subtitleEl ? subtitleEl.innerText.trim() : '';

                const locationEl = card.querySelector(
                    '.entity-result__secondary-subtitle, .subline-level-2'
                );
                const loc = locationEl ? locationEl.innerText.trim() : '';

                if (name && href.includes('linkedin.com')) {
                    items.push({ name, href, subtitle, location: loc });
                }
            });
            return items;
        }""")

        if not companies:
            break

        for co in companies:
            if len(results) >= max_results:
                break
            name = co.get("name", "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            results.append(co)

        # Next page
        try:
            nxt = page.locator('button[aria-label="Next"]')
            if await nxt.count() > 0 and await nxt.is_enabled():
                await nxt.click()
                await random_delay(2.5, 4.0)
                page_num += 1
            else:
                break
        except Exception:
            break

    return results


async def _google_linkedin_search(page, query: str, location: str, max_results: int) -> list[dict]:
    """
    Fallback: use DuckDuckGo to find LinkedIn company pages.
    Works without LinkedIn login.
    """
    results = []
    search = f'site:linkedin.com/company "{query}" "{location}"'
    url    = f"https://html.duckduckgo.com/html/?q={quote_plus(search)}"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await random_delay(1.5, 2.5)

        items = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('.result').forEach(r => {
                const a    = r.querySelector('a.result__a');
                const snip = r.querySelector('.result__snippet');
                if (a && a.href.includes('linkedin.com/company')) {
                    results.push({
                        name: a.innerText.trim(),
                        href: a.href,
                        subtitle: snip ? snip.innerText.trim() : '',
                    });
                }
            });
            return results;
        }""")

        results = items[:max_results]
        print(f"[linkedin] DuckDuckGo fallback: {len(results)} company pages found")
    except Exception as e:
        print(f"[linkedin] Fallback failed: {e}")

    return results


async def _get_company_website(page, linkedin_url: str) -> dict:
    """
    Visit a LinkedIn company page and extract the website URL.
    Works even without login for public pages.
    """
    result = {"website": "", "name": "", "description": ""}

    try:
        await page.goto(linkedin_url, wait_until="domcontentloaded", timeout=20000)
        await random_delay(2.0, 3.5)

        data = await page.evaluate("""() => {
            // Website link — visible on company page without login
            let website = '';
            document.querySelectorAll('a[href]').forEach(a => {
                const txt  = (a.innerText || '').toLowerCase().trim();
                const href = (a.href || '');
                // LinkedIn shows website in the "About" sidebar
                if ((txt === 'website' || txt.includes('company website') ||
                     a.getAttribute('data-control-name') === 'visit_company_website')
                    && !href.includes('linkedin.com')) {
                    website = href;
                }
            });

            // Company name
            const nameEl = document.querySelector(
                'h1.org-top-card-summary__title, .top-card-layout__title, '
                '[class*="top-card"] h1'
            );
            const name = nameEl ? nameEl.innerText.trim() : '';

            // Description
            const descEl = document.querySelector(
                '.org-page-details__definition-text, [class*="description"]'
            );
            const description = descEl ? descEl.innerText.trim().slice(0, 200) : '';

            return { website, name, description };
        }""")

        result = data

    except Exception as e:
        print(f"  [linkedin] Company page error: {str(e)[:60]}")

    return result


async def scrape_linkedin_companies(
    query: str, location: str, max_results: int, headless: bool
) -> list[dict]:
    """
    Main function: Search LinkedIn → get company pages →
    extract website → find email from website.
    """
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=get_proxy())
        ctx     = await create_stealth_context(browser, ua=random_ua())
        page    = await ctx.new_page()
        await patch_page(page)

        # Step 1: Find company LinkedIn pages
        companies = await _search_companies(page, query, location, max_results)
        print(f"[linkedin] Found {len(companies)} companies — extracting websites + emails...")

        # Step 2: For each company, get website + email
        for i, co in enumerate(companies):
            name         = co.get("name", "").strip()
            linkedin_url = co.get("href", "")
            subtitle     = co.get("subtitle", "")

            if not linkedin_url:
                continue

            print(f"\n  [{i+1}/{len(companies)}] {name[:45]}")

            # Get website from LinkedIn company page
            company_data = await _get_company_website(page, linkedin_url)
            website      = company_data.get("website", "")
            if not name:
                name = company_data.get("name", name)

            await random_delay(1.5, 3.0)

            # Find email via universal pipeline
            email_result = {"email": "", "method": "none", "confidence": "low"}
            if website or name:
                email_result = await find_email(
                    website=website,
                    business_name=name,
                    city=location,
                )

            row = {
                "business_name": name,
                "website":       website,
                "cta_url":       website,
                "email":         email_result.get("email", ""),
                "email_method":  email_result.get("method", ""),
                "phone":         "",
                "address":       co.get("location", location),
                "niche":         subtitle,
                "source":        "linkedin",
                "linkedin_url":  linkedin_url,
                "has_website":   "yes" if website else "no",
            }
            results.append(row)
            print(
                f"     website={'[OK]' if website else '[X]'} "
                f"email={'[OK] ' + row['email'][:30] if row['email'] else '[X]'}"
            )

        await browser.close()

    found_email = sum(1 for r in results if r.get("email"))
    print(f"\n[OK] LinkedIn: {len(results)} companies | {found_email} emails found")
    return results


def main():
    ap = argparse.ArgumentParser(description="LinkedIn company email extractor")
    ap.add_argument("--query",    required=True,  help='e.g. "real estate agency"')
    ap.add_argument("--location", default="",     help='e.g. "Dubai"')
    ap.add_argument("--max",      type=int, default=30)
    ap.add_argument("--out",      default="linkedin_leads.csv")
    ap.add_argument("--show",     action="store_true")
    args = ap.parse_args()

    rows = asyncio.run(
        scrape_linkedin_companies(args.query, args.location, args.max, not args.show)
    )

    if rows:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"[OK] Saved {len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
