"""
Instagram Business Lead Scraper
Scrapes hashtag pages to find business profiles with contact info.

Usage:
  python instagram_scraper.py --hashtag dubairealtor --max 100
  python instagram_scraper.py --hashtag londongyms --max 80 --user you@email.com --pass yourpassword
  python instagram_scraper.py --hashtags "dubairealtor,dubaiproperties,dubaiagent" --max 200

Output: instagram_leads.csv
Columns: business_name, instagram_url, bio, phone, email, website, cta_url, followers, niche_tag
"""

import asyncio
import argparse
import csv
import re
import sys
import random
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+\d{1,3}[\s\-]?)?(\(?\d{2,5}\)?[\s\-]?\d{3,5}[\s\-]?\d{3,5})")


def parse_bio(bio: str):
    emails = EMAIL_RE.findall(bio)
    phones = [m[0] + m[1] for m in PHONE_RE.findall(bio)]
    phones = [p.strip() for p in phones if len(re.sub(r"\D", "", p)) >= 7]
    return emails[:2], phones[:2]


async def login(page, username: str, password: str):
    print("[*] Logging in to Instagram...")
    await page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    try:
        await page.locator('input[name="username"]').fill(username)
        await page.locator('input[name="password"]').fill(password)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)

        # Dismiss "Save login info" prompt
        try:
            await page.locator("text=Not now").first.click(timeout=4000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        # Dismiss notifications prompt
        try:
            await page.locator("text=Not Now").first.click(timeout=4000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        print("[[OK]] Logged in")
        return True
    except Exception as e:
        print(f"[!] Login failed: {e}")
        return False


async def scrape_hashtag(page, hashtag: str, max_per_tag: int, seen: set, results: list):
    tag = hashtag.lstrip("#")
    url = f"https://www.instagram.com/explore/tags/{tag}/"
    print(f"\n[*] Scraping #{tag}")

    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    # Collect post links
    post_urls = set()
    scroll_rounds = 0
    while len(post_urls) < max_per_tag * 3 and scroll_rounds < 12:
        links = await page.locator('a[href*="/p/"]').all()
        for link in links:
            href = await link.get_attribute("href")
            if href and "/p/" in href:
                post_urls.add("https://www.instagram.com" + href if href.startswith("/") else href)
        await page.mouse.wheel(0, 2000)
        await page.wait_for_timeout(1500)
        scroll_rounds += 1

    print(f"  Found {len(post_urls)} posts — visiting profiles...")

    profile_urls_visited = set()
    collected = 0

    for post_url in list(post_urls):
        if collected >= max_per_tag:
            break
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

            # Get author profile link from post
            profile_link = await page.locator('a[role="link"][href*="/"]').first.get_attribute("href")
            if not profile_link:
                continue
            if profile_link.startswith("/"):
                profile_link = "https://www.instagram.com" + profile_link
            # Must be a profile URL (not /p/ or /explore/)
            if "/p/" in profile_link or "/explore/" in profile_link:
                continue

            if profile_link in profile_urls_visited or profile_link in seen:
                continue
            profile_urls_visited.add(profile_link)

            # Visit profile page
            await page.goto(profile_link, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # Extract profile data
            data = await page.evaluate("""
                () => {
                    // Username
                    const usernameEl = document.querySelector('h2, span._ap3a._aaco._aacw._aacx._aad7._aade');
                    const username = usernameEl ? usernameEl.innerText.trim() : window.location.pathname.replace(/\\//g,'');

                    // Full name
                    const nameEl = document.querySelector('span._ap3a._aaco._aacu._aacx._aad6._aade') ||
                                   document.querySelector('h1');
                    const fullname = nameEl ? nameEl.innerText.trim() : '';

                    // Bio
                    const bioEl = document.querySelector('h1 ~ div span, ._aacl._aaco._aacu._aacx._aad6._aade');
                    const bio = bioEl ? bioEl.innerText.trim() : '';

                    // Website link in profile
                    const webEl = document.querySelector('a[href]:not([href*="instagram.com"]):not([href^="#"])');
                    const website = webEl ? webEl.href : '';

                    // Follower count
                    const statsEls = document.querySelectorAll('li span span');
                    let followers = '';
                    statsEls.forEach(el => {
                        const parent = el.closest('li');
                        if (parent && parent.innerText.includes('follower')) {
                            followers = el.getAttribute('title') || el.innerText;
                        }
                    });

                    // Category (business accounts show this)
                    const catEl = document.querySelector('div._aa_7, span[class*="category"]');
                    const category = catEl ? catEl.innerText.trim() : '';

                    return { username, fullname, bio, website, followers, category };
                }
            """)

            bio  = data.get("bio", "")
            name = data.get("fullname") or data.get("username") or ""
            website = data.get("website", "")

            emails, phones = parse_bio(bio)

            row = {
                "business_name": name,
                "instagram_url":  profile_link,
                "instagram_user": data.get("username", ""),
                "bio":       bio[:300],
                "category":  data.get("category", ""),
                "followers": data.get("followers", ""),
                "email":    "; ".join(emails),
                "phone":    "; ".join(phones),
                "website":   website,
                "cta_url":   website or profile_link,
                "niche_tag": tag,
            }

            results.append(row)
            collected += 1
            seen.add(profile_link)

            has_contact = "[OK]" if (emails or phones or website) else "[X] no contact"
            print(f"  [{collected}] {name[:40]:<40} {has_contact}")

            await page.wait_for_timeout(random.randint(1500, 3000))

        except Exception as e:
            continue


async def run(hashtags: list, max_total: int, username: str, password: str, headless: bool, out: str):
    results = []
    seen    = set()
    per_tag = max(10, max_total // len(hashtags))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            ),
            viewport={"width": 390, "height": 844},
        )
        page = await ctx.new_page()

        if username and password:
            ok = await login(page, username, password)
            if not ok:
                print("[!] Continuing without login — limited data")
        else:
            print("[!] No login provided — some hashtag pages may be blocked")

        for tag in hashtags:
            await scrape_hashtag(page, tag, per_tag, seen, results)
            if len(results) >= max_total:
                break

        await browser.close()

    if not results:
        print("[!] No profiles found")
        return

    keys = ["business_name", "instagram_user", "instagram_url", "bio", "category",
            "followers", "email", "phone", "website", "cta_url", "niche_tag"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)
    print(f"\n[[OK]] Saved {len(results)} Instagram leads -> {out}")


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--hashtag",  help='Single hashtag e.g. "dubairealtor"')
    group.add_argument("--hashtags", help='Comma-separated e.g. "dubairealtor,dubaiproperties"')
    ap.add_argument("--max",   type=int, default=100,              help="Max total profiles (default 100)")
    ap.add_argument("--out",   default="instagram_leads.csv",      help="Output CSV path")
    ap.add_argument("--user",  default=None,                       help="Instagram username (recommended)")
    ap.add_argument("--pass",  dest="password", default=None,      help="Instagram password")
    ap.add_argument("--show",  action="store_true",                help="Show browser window")
    args = ap.parse_args()

    tags = [t.strip().lstrip("#") for t in (args.hashtags or args.hashtag).split(",")]

    asyncio.run(run(tags, args.max, args.user, args.password, headless=not args.show, out=args.out))


if __name__ == "__main__":
    main()
