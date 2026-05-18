"""
AI News Aggregator — pulls latest AI updates from 15+ sources worldwide.
Sources: Anthropic, OpenAI, NVIDIA, Product Hunt, Product Sumo, TechCrunch,
VentureBeat, MIT Tech Review, Ars Technica, Hacker News, Reddit AI subs,
Google AI, Meta AI, DeepMind, Hugging Face + more.

Usage:
    python ai_news_scraper.py                                    # all sources
    python ai_news_scraper.py --sources producthunt,openai       # specific sources
    python ai_news_scraper.py --keyword "NVIDIA" --max 50        # keyword filter
    python ai_news_scraper.py --output ai_news.csv               # save to CSV
    python ai_news_scraper.py --continuous --interval 30         # run every 30 min
    python ai_news_scraper.py --show                             # show browser for JS sites
"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

RUN_LOG = []


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    RUN_LOG.append(line)


TEXT_CACHE = {}


async def fetch_text(url: str, timeout: int = 15) -> str:
    if url in TEXT_CACHE:
        return TEXT_CACHE[url]
    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            TEXT_CACHE[url] = text
            return text
    except Exception as e:
        log(f"  [WARN] fetch failed: {url[:60]}... — {e}")
        TEXT_CACHE[url] = ""
        return ""


async def fetch_json(url: str, timeout: int = 15) -> dict | list | None:
    try:
        import json
        text = await fetch_text(url, timeout)
        return json.loads(text) if text else None
    except Exception:
        return None


def parse_rss(xml_text: str, source_name: str) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            desc = item.findtext("description", "")
            creator = item.findtext("dc:creator", "") or item.findtext(
                "{http://purl.org/dc/elements/1.1/}creator", ""
            )
            content_enc = item.findtext("content:encoded", "") or item.findtext(
                "{http://purl.org/rss/1.0/modules/content/}encoded", ""
            )
            summary = (desc or content_enc or "")[:500]
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            articles.append(
                {
                    "title": title.strip(),
                    "url": link.strip(),
                    "published": pub_date.strip(),
                    "summary": summary,
                    "author": creator.strip(),
                    "source": source_name,
                }
            )
    except ET.ParseError as e:
        log(f"  [WARN] RSS parse error for {source_name}: {e}")
    return articles


def parse_atom(xml_text: str, source_name: str) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (
                entry.findtext("{http://www.w3.org/2005/Atom}title", "")
                or entry.findtext("atom:title", "", ns)
            )
            link_el = entry.find(
                "{http://www.w3.org/2005/Atom}link"
            ) or entry.find("atom:link", ns)
            link = link_el.get("href", "").strip() if link_el is not None else ""
            published = (
                entry.findtext("{http://www.w3.org/2005/Atom}published", "")
                or entry.findtext("{http://www.w3.org/2005/Atom}updated", "")
                or entry.findtext("atom:published", "", ns)
                or entry.findtext("atom:updated", "", ns)
            )
            summary = (
                entry.findtext("{http://www.w3.org/2005/Atom}summary", "")
                or entry.findtext("atom:summary", "", ns)
            )[:500]
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            author_el = entry.find("{http://www.w3.org/2005/Atom}author")
            author = (
                author_el.findtext("{http://www.w3.org/2005/Atom}name", "")
                if author_el is not None
                else ""
            )
            articles.append(
                {
                    "title": title.strip(),
                    "url": link,
                    "published": published,
                    "summary": summary,
                    "author": author,
                    "source": source_name,
                }
            )
    except ET.ParseError as e:
        log(f"  [WARN] Atom parse error for {source_name}: {e}")
    return articles


def parse_html_meta(html_text: str, url: str, source_name: str) -> list[dict]:
    articles = []
    if not html_text:
        return articles
    try:
        from html.parser import HTMLParser

        class ArticleFinder(HTMLParser):
            def __init__(self):
                super().__init__()
                self.titles = []
                self.in_title = False
                self.in_article = False
                self.current_tag = ""
                self.articles_data = []
                self.current = {}

            def handle_starttag(self, tag, attrs):
                self.current_tag = tag
                attrs_dict = dict(attrs)
                classes = attrs_dict.get("class", "")

                # Find article headlines
                if tag in ("h1", "h2", "h3", "h4"):
                    self.in_title = True

            def handle_data(self, data):
                if self.in_title and len(data.strip()) > 20:
                    self.titles.append(data.strip())

            def handle_endtag(self, tag):
                if tag in ("h1", "h2", "h3", "h4"):
                    self.in_title = False

        finder = ArticleFinder()
        finder.feed(html_text)
        for title in finder.titles:
            articles.append(
                {
                    "title": title,
                    "url": url,
                    "published": "",
                    "summary": "",
                    "author": "",
                    "source": source_name,
                }
            )
    except Exception:
        pass
    return articles if articles else [{"title": "Unknown", "url": url, "published": "", "summary": "", "author": "", "source": source_name}]


# ── Source definitions ──────────────────────────────────────────────────────────

SOURCES = OrderedDict(
    {
        # ── RSS/Atom feeds (fast, no browser needed) ──────────────────────
        "openai": {
            "type": "rss",
            "url": "https://openai.com/blog/news.xml",
            "label": "OpenAI Blog",
        },
        "anthropic": {
            "type": "rss",
            "url": "https://www.anthropic.com/feed.xml",
            "label": "Anthropic Blog",
        },
        "google_ai": {
            "type": "rss",
            "url": "https://blog.google/technology/ai/rss/",
            "label": "Google AI Blog",
        },
        "deepmind": {
            "type": "rss",
            "url": "https://deepmind.google/blog/rss/",
            "label": "DeepMind Blog",
        },
        "meta_ai": {
            "type": "rss",
            "url": "https://ai.meta.com/blog/rss/",
            "label": "Meta AI Blog",
        },
        "nvidia": {
            "type": "rss",
            "url": "https://blogs.nvidia.com/feed/",
            "label": "NVIDIA Blog",
        },
        "techcrunch_ai": {
            "type": "rss",
            "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
            "label": "TechCrunch AI",
        },
        "venturebeat_ai": {
            "type": "rss",
            "url": "https://venturebeat.com/category/ai/feed/",
            "label": "VentureBeat AI",
        },
        "mit_tech_review": {
            "type": "rss",
            "url": "https://www.technologyreview.com/topic/artificial-intelligence/rss/",
            "label": "MIT Tech Review AI",
        },
        "ars_technica_ai": {
            "type": "rss",
            "url": "https://feeds.arstechnica.com/arstechnica/ai",
            "label": "Ars Technica AI",
        },
        "hackernews": {
            "type": "rss",
            "url": "https://hnrss.org/frontpage?points=50",
            "label": "Hacker News",
        },
        "reddit_artificial": {
            "type": "rss",
            "url": "https://www.reddit.com/r/artificial/.rss",
            "label": "Reddit r/artificial",
        },
        "reddit_machinelearning": {
            "type": "rss",
            "url": "https://www.reddit.com/r/MachineLearning/.rss",
            "label": "Reddit r/MachineLearning",
        },
        "reddit_singularity": {
            "type": "rss",
            "url": "https://www.reddit.com/r/singularity/.rss",
            "label": "Reddit r/singularity",
        },
        "huggingface": {
            "type": "rss",
            "url": "https://huggingface.co/blog/feed.xml",
            "label": "Hugging Face Blog",
        },
        "together_ai": {
            "type": "rss",
            "url": "https://www.together.ai/blog/rss.xml",
            "label": "Together AI Blog",
        },
        # ── Playwright-based sources (JS rendered) ────────────────────────
        "producthunt": {
            "type": "playwright",
            "url": "https://www.producthunt.com/",
            "label": "Product Hunt",
            "selector": "a[href*='/posts/']",
        },
        "producthunt_ai": {
            "type": "playwright",
            "url": "https://www.producthunt.com/topics/artificial-intelligence",
            "label": "Product Hunt AI",
            "selector": "a[href*='/posts/']",
        },
    }
)


# ── Keyword categories ─────────────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    "llm": [
        "gpt", "claude", "llama", "mistral", "gemini", "qwen", "deepseek",
        "language model", "transformer", "open source model", "foundation model",
    ],
    "ai_agent": [
        "agent", "autonomous", "tool use", "function calling", "computer use",
        "agentic", "swarm", "multi-agent",
    ],
    "ai_hardware": [
        "nvidia", "h100", "b200", "gpu", "chip", "semiconductor", "training chip",
        "inference", "amd", "intel", "ai accelerator", "tpu",
    ],
    "robotics": [
        "robot", "humanoid", "robotaxi", "self-driving", "autonomous vehicle",
        "figure", "tesla bot", "optimus", "spot", "atlas",
    ],
    "ai_healthcare": [
        "ai health", "medical ai", "drug discovery", "ai diagnosis", "radiology ai",
        "biotech", "genomics", "protein folding",
    ],
    "ai_finance": [
        "ai banking", "fintech", "trading bot", "ai finance", "fraud detection",
        "algorithmic trading",
    ],
    "ai_images_video": [
        "sora", "dall-e", "midjourney", "stable diffusion", "video generation",
        "image generation", "flux", "synthesis", "runway", "pika",
    ],
    "ai_code": [
        "copilot", "cursor", "code generation", "ai coding", "devon", "devin",
        "claude code", "codex",
    ],
}


async def scrape_source(
    source_id: str, source_config: dict, headless: bool
) -> list[dict]:
    source_type = source_config.get("type", "rss")
    source_name = source_config.get("label", source_id)
    url = source_config.get("url", "")
    if not url:
        return []

    log(f"[*] {source_name} ({source_id})")

    if source_type == "rss":
        xml_text = await fetch_text(url)
        articles = parse_rss(xml_text, source_name)
        if not articles:
            articles = parse_atom(xml_text, source_name)
        if not articles:
            articles = parse_html_meta(xml_text, url, source_name)
        log(f"  -> {len(articles)} articles")
        return articles

    elif source_type == "playwright":
        articles = await scrape_with_playwright(
            url, source_name, source_config.get("selector", "article a"),
            headless,
        )
        log(f"  -> {len(articles)} articles")
        return articles

    return []


async def scrape_with_playwright(
    url: str, source_name: str, selector: str, headless: bool
) -> list[dict]:
    articles = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1400, "height": 900},
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Product Hunt specific: wait for posts to load
            if "producthunt" in url:
                await page.wait_for_timeout(5000)
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(2000)

            # Try to find links
            seen_titles = set()
            links = await page.locator(selector).all()
            for link in links[:50]:
                try:
                    title = (await link.inner_text()).strip()
                    href = await link.get_attribute("href")
                    if not title or not href or len(title) < 10:
                        continue
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    full_url = (
                        href
                        if href.startswith("http")
                        else f"https://www.producthunt.com{href}"
                    )
                    articles.append(
                        {
                            "title": title,
                            "url": full_url,
                            "published": "",
                            "summary": "",
                            "author": "",
                            "source": source_name,
                        }
                    )
                except Exception:
                    continue

            if len(articles) < 5:
                all_links = await page.locator("a").all()
                for link in all_links:
                    try:
                        title = (await link.inner_text()).strip()
                        href = await link.get_attribute("href")
                        if not title or not href or len(title) < 15:
                            continue
                        if title in seen_titles:
                            continue
                        if any(
                            kw in href
                            for kw in [
                                "/posts/",
                                "/launches/",
                                "/products/",
                            ]
                        ):
                            seen_titles.add(title)
                            full_url = (
                                href
                                if href.startswith("http")
                                else f"https://www.producthunt.com{href}"
                            )
                            articles.append(
                                {
                                    "title": title,
                                    "url": full_url,
                                    "published": "",
                                    "summary": "",
                                    "author": "",
                                    "source": source_name,
                                }
                            )
                    except Exception:
                        continue

            await browser.close()
    except Exception as e:
        log(f"  [WARN] Playwright error for {source_name}: {e}")

    return articles[:30]


def extract_topics(title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".lower()
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            topics.append(topic)
    return topics if topics else ["general"]


def deduplicate(articles: list[dict]) -> list[dict]:
    seen_titles = set()
    unique = []
    for a in articles:
        key = re.sub(r"[^a-z0-9]", "", a.get("title", "").lower())[:60]
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)
    return unique


def filter_by_keyword(articles: list[dict], keyword: str) -> list[dict]:
    kw = keyword.lower()
    return [
        a
        for a in articles
        if kw in a.get("title", "").lower()
        or kw in a.get("summary", "").lower()
    ]


def filter_by_country(articles: list[dict], country_code: str) -> list[dict]:
    country_map = {
        "us": r"united states|usa|u\.s\.|america|new york|san francisco|california|silicon valley",
        "uk": "united kingdom|london|uk|england|britain",
        "ae": "dubai|uae|abu dhabi|united arab emirates",
        "in": "india|bengaluru|mumbai|delhi|bangalore",
        "cn": "china|beijing|shanghai|shenzhen|hong kong",
        "sg": "singapore",
        "jp": "japan|tokyo",
        "de": "germany|berlin|munich",
        "fr": "france|paris",
        "ca": "canada|toronto|vancouver",
    }
    pattern = country_map.get(country_code.lower())
    if not pattern:
        return articles
    regex = re.compile(pattern, re.IGNORECASE)
    return [
        a
        for a in articles
        if regex.search(a.get("title", "") + " " + a.get("summary", ""))
    ]


# ── Export ─────────────────────────────────────────────────────────────────────


def to_csv(articles: list[dict], path: str):
    if not articles:
        log("[!] No articles to save")
        return
    keys = [
        "title", "url", "published", "summary", "author",
        "source", "topics",
    ]
    for a in articles:
        a["topics"] = "; ".join(extract_topics(a.get("title", ""), a.get("summary", "")))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(articles)
    log(f"[[OK]] Saved {len(articles)} articles -> {path}")


def to_json(articles: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)
    log(f"[[OK]] Saved {len(articles)} articles -> {path}")


def to_markdown(articles: list[dict]) -> str:
    lines = ["# AI News — Latest Updates\n", f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]
    for i, a in enumerate(articles[:30], 1):
        topics = "; ".join(extract_topics(a.get("title", ""), a.get("summary", "")))
        lines.append(f"## {i}. {a['title']}")
        lines.append(f"**Source:** {a['source']} | **Topics:** {topics}")
        if a.get("published"):
            lines.append(f"**Published:** {a['published']}")
        if a.get("summary"):
            lines.append(f"\n{a['summary'][:300]}...")
        lines.append(f"\n🔗 [Read more]({a['url']})\n")
    return "\n".join(lines)


# ── Main Orchestrator ──────────────────────────────────────────────────────────


async def run(
    sources_filter: list[str] | None = None,
    keyword: str = "",
    max_articles: int = 100,
    headless: bool = True,
    country_code: str = "",
):
    all_articles = []
    source_items = list(SOURCES.items())

    if sources_filter:
        source_items = [(k, v) for k, v in source_items if k in sources_filter]
        missing = set(sources_filter) - {k for k, _ in source_items}
        if missing:
            log(f"[WARN] Unknown sources: {missing}")

    for source_id, source_config in source_items:
        try:
            articles = await scrape_source(source_id, source_config, headless)
            all_articles.extend(articles)
        except Exception as e:
            log(f"[ERROR] {source_config['label']}: {e}")
            continue

    all_articles = deduplicate(all_articles)

    if keyword:
        all_articles = filter_by_keyword(all_articles, keyword)

    if country_code:
        all_articles = filter_by_country(all_articles, country_code)

    # Sort: newest first (rough heuristic — RSS feeds put newest first)
    all_articles = all_articles[:max_articles]

    return all_articles


def main():
    ap = argparse.ArgumentParser(description="AI News Aggregator")
    ap.add_argument(
        "--sources",
        default=None,
        help=f"Comma-separated sources: {', '.join(SOURCES.keys())} (default: all)",
    )
    ap.add_argument("--keyword", default="", help="Filter by keyword (e.g. 'NVIDIA')")
    ap.add_argument("--country", default="", help="Filter by country code (US, IN, CN, AE...)")
    ap.add_argument("--max", type=int, default=100, help="Max articles (default 100)")
    ap.add_argument("--output", default="", help="Output file (auto-detects format from extension)")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    ap.add_argument("--md", action="store_true", help="Output as Markdown")
    ap.add_argument("--show", action="store_true", help="Show browser (for JS-rendered sites)")
    ap.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously every --interval minutes",
    )
    ap.add_argument("--interval", type=int, default=30, help="Minutes between runs (default 30)")
    args = ap.parse_args()

    sources = args.sources.split(",") if args.sources else None

    async def run_once():
        articles = await run(
            sources_filter=sources,
            keyword=args.keyword,
            max_articles=args.max,
            headless=not args.show,
            country_code=args.country,
        )

        if not articles:
            log("[!] No articles found. Try --show to debug.")
            return articles

        topics_count = {}
        for a in articles:
            for t in extract_topics(a.get("title", ""), a.get("summary", "")):
                topics_count[t] = topics_count.get(t, 0) + 1

        print(f"\n{'='*55}")
        print(f"  Total articles: {len(articles)}")
        print(f"  Topics: {', '.join(f'{k}={v}' for k, v in sorted(topics_count.items(), key=lambda x: -x[1]))}")
        print(f"{'='*55}\n")

        # Print top 20
        for i, a in enumerate(articles[:20], 1):
            topics = ", ".join(extract_topics(a.get("title", ""), a.get("summary", "")))
            src = a.get("source", "?")
            print(f"  {i:2d}. [{src:<18}] {a['title'][:80]}")
            if topics and topics != "general":
                print(f"      topics: {topics}")

        # Save output
        out_path = args.output
        if out_path:
            if out_path.endswith(".json") or args.json:
                to_json(articles, out_path)
            elif out_path.endswith(".md") or args.md:
                md = to_markdown(articles)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md)
                log(f"[[OK]] Saved Markdown -> {out_path}")
            else:
                to_csv(articles, out_path)
        elif args.json:
            to_json(articles, "ai_news.json")
        elif args.md:
            md = to_markdown(articles)
            with open("ai_news.md", "w", encoding="utf-8") as f:
                f.write(md)
            log(f"[[OK]] Saved Markdown -> ai_news.md")
        else:
            to_csv(articles, "ai_news.csv")

        return articles

    if args.continuous:
        log(f"=== Continuous mode — every {args.interval} min ===")
        while True:
            asyncio.run(run_once())
            log(f"\nSleeping {args.interval} min...\n")
            time.sleep(args.interval * 60)
    else:
        asyncio.run(run_once())


if __name__ == "__main__":
    main()
