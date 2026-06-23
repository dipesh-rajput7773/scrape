"""
Enrich scraped leads: visit each cta_url, extract email + phone + IG handle.
Preserves existing phone/email from Maps scraper — only fills if empty.
Also tries /contact page if main page yields nothing.
Usage: python enrich.py leads.csv enriched.csv
"""

import asyncio
import csv
import re
import sys
from playwright.async_api import async_playwright
from stealth import (
    create_stealth_context, patch_page, random_delay, get_proxy,
    random_ua, random_viewport,
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{7,}\d)")
IG_RE    = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})(?:/|\"|\s)")
LI_RE    = re.compile(r"linkedin\.com/(?:in|company)/([A-Za-z0-9_\-%.]+)")
FB_RE    = re.compile(r"facebook\.com/([A-Za-z0-9_\-%.]+)")

JUNK_EMAILS = (".png", ".jpg", ".svg", ".gif", ".webp", "sentry", "wix.com",
               "example.com", "domain.com", "email.com", "yourcompany")


def clean_emails(raw: list[str]) -> list[str]:
    out = []
    for e in raw:
        e = e.lower().strip()
        if any(j in e for j in JUNK_EMAILS):
            continue
        if len(e) > 6 and "@" in e and "." in e.split("@")[1]:
            out.append(e)
    return list(dict.fromkeys(out))  # dedupe, preserve order


def clean_phones(raw: list[str]) -> list[str]:
    out = []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15:
            out.append(p.strip())
    return list(dict.fromkeys(out))


async def try_contact_page(page, base_url: str) -> str:
    """Try /contact or /contact-us if main page gave no email."""
    for suffix in ["/contact", "/contact-us", "/about", "/about-us", "/reach-us"]:
        try:
            url = base_url.rstrip("/") + suffix
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(800)
            html = await page.content()
            emails = clean_emails(EMAIL_RE.findall(html))
            if emails:
                return html
        except Exception:
            continue
    return ""


async def scrape_about_text(page, base_url: str) -> str:
    """Find About page and extract meaningful text for AI personalization."""
    for suffix in ["/about", "/about-us", "/our-story", "/company"]:
        try:
            url = base_url.rstrip("/") + suffix
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1000)
            text = await page.evaluate("""() => {
                const main = document.querySelector('main, article, #content, .content');
                return (main ? main.innerText : document.body.innerText).slice(0, 2000);
            }""")
            if len(text) > 200:
                return text.strip()
        except Exception:
            continue
    return ""


async def enrich(rows):
    # Use email_finder's batch processor for email extraction
    # It runs the full 5-step pipeline: website scan → dork → pattern → hunter
    try:
        from email_finder import find_emails_batch
        rows = await find_emails_batch(rows, concurrency=3)
    except Exception as e:
        print(f"[enrich] email_finder batch failed, falling back: {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy=get_proxy())
        ctx = await create_stealth_context(browser, viewport=random_viewport(), ua=random_ua())
        page = await ctx.new_page()
        await patch_page(page)

        for i, row in enumerate(rows, 1):
            url = row.get("cta_url", "").strip() or row.get("website", "").strip()

            # Preserve existing Maps phone — don't reset it
            existing_phone = row.get("phone", "").strip()
            existing_email = row.get("email", "").strip()

            row.setdefault("email", "")
            row.setdefault("phone", "")
            row.setdefault("instagram", "")
            row.setdefault("linkedin", "")
            row.setdefault("facebook", "")

            if not url or not url.startswith("http"):
                print(f"[{i}/{len(rows)}] SKIP (no URL) — {row.get('business_name','')[:40]}")
                continue

            try:
                print(f"[{i}/{len(rows)}] {url[:70]}")
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await random_delay(1.2, 2.5)
                html = await page.content()

                emails = clean_emails(EMAIL_RE.findall(html))
                phones = clean_phones(PHONE_RE.findall(html))
                igs    = list(dict.fromkeys(IG_RE.findall(html)))
                lis    = list(dict.fromkeys(LI_RE.findall(html)))
                fbs    = list(dict.fromkeys(FB_RE.findall(html)))

                # If no email/socials on main page, try /contact
                if not emails or not (igs or lis or fbs):
                    html2 = await try_contact_page(page, url)
                    if html2:
                        emails = list(dict.fromkeys(emails + clean_emails(EMAIL_RE.findall(html2))))
                        phones = phones or clean_phones(PHONE_RE.findall(html2))
                        igs    = list(dict.fromkeys(igs + IG_RE.findall(html2)))
                        lis    = list(dict.fromkeys(lis + LI_RE.findall(html2)))
                        fbs    = list(dict.fromkeys(fbs + FB_RE.findall(html2)))

                # Merge with existing data — don't overwrite if already have value
                if emails:
                    row["email"] = "; ".join(emails[:3])
                elif existing_email:
                    row["email"] = existing_email

                if phones:
                    # Merge Maps phone + website phone
                    all_phones = ([existing_phone] if existing_phone else []) + phones
                    row["phone"] = "; ".join(list(dict.fromkeys(all_phones))[:3])
                elif existing_phone:
                    row["phone"] = existing_phone

                if igs:
                    ig_clean = [h for h in igs if h not in ("p", "explore", "reel", "stories")]
                    row["instagram"] = "; ".join(ig_clean[:2])

                if lis:
                    li_clean = [h for h in lis if h not in ("company", "in", "pub", "feed", "share")]
                    row["linkedin"] = "; ".join(li_clean[:2])

                if fbs:
                    fb_clean = [h for h in fbs if h not in ("pages", "group", "people", "sharer", "profile.php")]
                    row["facebook"] = "; ".join(fb_clean[:2])

                # Hyper-personalization: Scrape About text
                row["about_text"] = await scrape_about_text(page, url)

                status = []
                if row["email"]:   status.append(f"email=[OK]")
                if row["phone"]:   status.append(f"phone=[OK]")
                if row["instagram"]: status.append(f"ig=[OK]")
                if row["linkedin"]:  status.append(f"li=[OK]")
                if row["facebook"]:  status.append(f"fb=[OK]")
                if row["about_text"]: status.append(f"about=[OK]")
                print(f"  -> {' '.join(status) or 'no contact found'}")

            except Exception as e:
                # On redirect/timeout errors, still keep existing Maps data
                row["phone"] = existing_phone
                row["email"] = existing_email
                print(f"  [!] {str(e)[:80]}")
                continue

        await browser.close()
    return rows



def main():
    if len(sys.argv) < 3:
        print("Usage: python enrich.py leads.csv enriched.csv")
        sys.exit(1)

    inp, out = sys.argv[1], sys.argv[2]
    with open(inp, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows = asyncio.run(enrich(rows))

    keys = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    with_email = sum(1 for r in rows if r.get("email"))
    with_phone = sum(1 for r in rows if r.get("phone"))
    print(f"[[OK]] Enriched {len(rows)} leads -> {out}")
    print(f"       Email: {with_email}  Phone: {with_phone}")


if __name__ == "__main__":
    main()
