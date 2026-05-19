from __future__ import annotations
﻿"""
Reddit Lead Scraper — finds business owners actively looking for automation/chatbots.
Uses Reddit public JSON API (no API key needed, free, unlimited).

These are INBOUND leads — people posting their exact problem -> easiest to close.

Usage:
  python reddit_scraper.py --niche realestate --max 100
  python reddit_scraper.py --niche gym --subreddits "Entrepreneur,smallbusiness" --max 150
  python reddit_scraper.py --keywords "whatsapp bot,lead automation" --max 200

Output: reddit_leads.csv
Columns: business_name, post_title, pain_point, reddit_url, subreddit, email, cta_url, score
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from urllib.parse import quote

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_RE   = re.compile(r"https?://(?!reddit\.com|redd\.it)[^\s)>\]]+")


# ── Niche config ──────────────────────────────────────────────────────────────

NICHE_CONFIG = {
    "realestate": {
        "subreddits": ["realestate", "RealEstateInvesting", "landlord", "REBubble",
                       "realtors", "CommercialRealEstate"],
        "keywords": ["lead follow up", "crm automation", "whatsapp leads", "automate leads",
                     "chatbot real estate", "lead management", "automate follow up",
                     "lead nurturing", "losing leads", "too many leads"],
    },
    "dental": {
        "subreddits": ["Dentistry", "DentalHygiene", "smallbusiness", "medical"],
        "keywords": ["appointment reminder", "no shows dental", "automate appointments",
                     "patient follow up", "dental software", "booking automation",
                     "reminder system", "reduce no shows"],
    },
    "gym": {
        "subreddits": ["gymowners", "EntrepreneurRideAlong", "Entrepreneur", "smallbusiness"],
        "keywords": ["gym leads", "membership sales", "automate gym", "fitness chatbot",
                     "lead follow up gym", "whatsapp marketing", "gym software",
                     "trial class automation", "fitness studio automation"],
    },
    "salon": {
        "subreddits": ["hairstylist", "smallbusiness", "Entrepreneur"],
        "keywords": ["salon booking", "automate appointments", "client reminders",
                     "no show salon", "booking software", "whatsapp salon"],
    },
    "it": {
        "subreddits": ["msp", "sysadmin", "ITManagers", "smallbusiness", "Entrepreneur"],
        "keywords": ["automate onboarding", "ticket automation", "workflow automation",
                     "n8n", "make automation", "zapier alternative", "automate reports",
                     "it automation", "process automation"],
    },
    "ecom": {
        "subreddits": ["shopify", "ecommerce", "FulfillmentByAmazon", "Entrepreneur"],
        "keywords": ["abandoned cart", "whatsapp ecommerce", "automate orders",
                     "customer follow up", "ecommerce automation", "cart recovery",
                     "order notification whatsapp"],
    },
    "general": {
        "subreddits": ["Entrepreneur", "smallbusiness", "EntrepreneurRideAlong",
                       "startups", "business", "marketing"],
        "keywords": ["whatsapp bot", "chatbot for business", "automate follow up",
                     "lead automation", "workflow automation", "ai chatbot",
                     "whatsapp automation", "automate my business", "save time automation",
                     "need automation", "looking for chatbot"],
    },
}


# ── Reddit API (no auth needed) ───────────────────────────────────────────────

HEADERS = {"User-Agent": "Mozilla/5.0 LeadScraper/1.0"}


def reddit_get(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [!] Request failed: {url[:60]}... — {e}")
        return None


def search_subreddit(subreddit: str, keyword: str, limit: int = 25) -> list[dict]:
    url = (
        f"https://www.reddit.com/r/{subreddit}/search.json"
        f"?q={quote(keyword)}&restrict_sr=1&sort=new&limit={limit}&t=year"
    )
    data = reddit_get(url)
    if not data:
        return []
    try:
        return data["data"]["children"]
    except Exception:
        return []


def search_all(keyword: str, limit: int = 25) -> list[dict]:
    url = (
        f"https://www.reddit.com/search.json"
        f"?q={quote(keyword)}&sort=new&limit={limit}&t=year&type=link"
    )
    data = reddit_get(url)
    if not data:
        return []
    try:
        return data["data"]["children"]
    except Exception:
        return []


def extract_lead(post: dict, keyword_hit: str) -> dict | None:
    d     = post.get("data", {})
    title = d.get("title", "")
    body  = d.get("selftext", "")
    text  = f"{title} {body}"

    # Skip: very short posts, removed posts, or purely asking questions with no business context
    if len(body) < 20 and len(title) < 30:
        return None
    if "[removed]" in body or "[deleted]" in body:
        return None

    # Extract contact info from post
    emails   = EMAIL_RE.findall(text)
    ext_urls = URL_RE.findall(text)
    # Filter out image/reddit URLs
    ext_urls = [u for u in ext_urls if not any(x in u for x in [".jpg", ".png", ".gif", "imgur", "i.redd"])]

    author   = d.get("author", "")
    sub      = d.get("subreddit", "")
    post_url = f"https://www.reddit.com{d.get('permalink', '')}"
    score    = d.get("score", 0)

    # Use first external URL as their website
    website = ext_urls[0] if ext_urls else ""

    return {
        "business_name": f"u/{author}",
        "author":        author,
        "post_title":    title[:200],
        "pain_point":    body[:400].replace("\n", " "),
        "keyword_hit":   keyword_hit,
        "subreddit":     sub,
        "reddit_url":    post_url,
        "email":         "; ".join(emails[:2]),
        "phone":         "",
        "website":       website,
        "cta_url":       website or post_url,
        "score":         score,
        "source":        "reddit",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape(niche: str, custom_keywords: list, custom_subreddits: list, max_results: int) -> list[dict]:
    config     = NICHE_CONFIG.get(niche, NICHE_CONFIG["general"])
    subreddits = custom_subreddits or config["subreddits"]
    keywords   = custom_keywords   or config["keywords"]

    results = []
    seen    = set()

    for keyword in keywords:
        if len(results) >= max_results:
            break

        print(f"\n[*] Keyword: '{keyword}'")

        # Search across all target subreddits
        for sub in subreddits:
            if len(results) >= max_results:
                break
            posts = search_subreddit(sub, keyword, limit=25)
            for post in posts:
                if len(results) >= max_results:
                    break
                post_id = post.get("data", {}).get("id")
                if not post_id or post_id in seen:
                    continue
                seen.add(post_id)
                lead = extract_lead(post, keyword)
                if lead:
                    results.append(lead)
                    print(f"  [{len(results)}] r/{lead['subreddit']:<20} {lead['post_title'][:55]}")
            time.sleep(0.8)  # Be polite to Reddit API

        # Also search globally
        posts = search_all(keyword, limit=20)
        for post in posts:
            if len(results) >= max_results:
                break
            post_id = post.get("data", {}).get("id")
            if not post_id or post_id in seen:
                continue
            seen.add(post_id)
            lead = extract_lead(post, keyword)
            if lead:
                results.append(lead)
                print(f"  [{len(results)}] r/{lead['subreddit']:<20} {lead['post_title'][:55]}")
        time.sleep(1)

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niche",       default="general",
                    choices=list(NICHE_CONFIG.keys()),
                    help="Target niche (default: general)")
    ap.add_argument("--keywords",    default=None,
                    help='Custom keywords comma-separated e.g. "whatsapp bot,lead automation"')
    ap.add_argument("--subreddits",  default=None,
                    help='Custom subreddits comma-separated e.g. "Entrepreneur,smallbusiness"')
    ap.add_argument("--max",         type=int, default=200,
                    help="Max leads (default 200)")
    ap.add_argument("--out",         default="reddit_leads.csv",
                    help="Output CSV path")
    args = ap.parse_args()

    custom_kw  = [k.strip() for k in args.keywords.split(",")]   if args.keywords   else []
    custom_sub = [s.strip() for s in args.subreddits.split(",")] if args.subreddits else []

    results = scrape(args.niche, custom_kw, custom_sub, args.max)

    if not results:
        print("[!] No leads found")
        sys.exit(0)

    keys = ["business_name", "author", "post_title", "pain_point", "keyword_hit",
            "subreddit", "reddit_url", "email", "phone", "website", "cta_url", "score", "source"]
    for r in results:
        for k in keys:
            r.setdefault(k, "")

    # Sort by score descending (higher score = more engagement = more relevant)
    results.sort(key=lambda x: int(x.get("score", 0) or 0), reverse=True)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)

    with_contact = sum(1 for r in results if r.get("email") or r.get("website"))
    print(f"\n[[OK]] Saved {len(results)} Reddit leads -> {args.out}")
    print(f"    {with_contact} have email/website (best for outreach)")


if __name__ == "__main__":
    main()
