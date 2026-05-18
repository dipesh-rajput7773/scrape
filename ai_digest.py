"""
AI News Digest — daily/weekly AI news report generator.
Fetches ALL major AI news (no keyword needed), compiles into:
  - PowerPoint (.pptx) — presentation-ready
  - Markdown (.md) — readable doc
  - CSV / JSON — raw data

Usage:
    python ai_digest.py                              # daily digest (last 24h equiv.)
    python ai_digest.py --mode weekly                 # weekly digest
    python ai_digest.py --format pptx                 # PowerPoint only
    python ai_digest.py --format md                   # Markdown only
    python ai_digest.py --format all                  # all formats
    python ai_digest.py --outdir ./reports            # custom output dir
    python ai_digest.py --sources openai,anthropic    # specific sources
"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from ai_news_scraper import SOURCES, TOPIC_KEYWORDS, run as fetch_news, extract_topics


def generate_pptx(articles: list[dict], out_path: str, date_range: str):
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    W = prs.slide_width
    H = prs.slide_height

    # ── Colors ────────────────────────────────────────────────────────────
    BG_DARK = RGBColor(0x1A, 0x1A, 0x2E)
    BG_CARD = RGBColor(0x22, 0x22, 0x3A)
    ACCENT = RGBColor(0x00, 0xD2, 0xFF)
    ACCENT2 = RGBColor(0x7C, 0x3A, 0xED)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    GRAY = RGBColor(0xAA, 0xAA, 0xAA)
    TOPIC_COLORS = {
        "llm": RGBColor(0x00, 0xD2, 0xFF),
        "ai_agent": RGBColor(0x7C, 0x3A, 0xED),
        "ai_hardware": RGBColor(0x00, 0xE6, 0x76),
        "robotics": RGBColor(0xFF, 0x6B, 0x6B),
        "ai_healthcare": RGBColor(0xFF, 0xA5, 0x00),
        "ai_finance": RGBColor(0x50, 0xC8, 0x78),
        "ai_images_video": RGBColor(0xFF, 0x69, 0xB4),
        "ai_code": RGBColor(0x00, 0xBF, 0xBF),
        "general": GRAY,
    }

    def add_bg(slide, color=BG_DARK):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = color

    def add_textbox(slide, left, top, width, height, text, size=14,
                    bold=False, color=WHITE, align=PP_ALIGN.LEFT, font_name="Calibri"):
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color
        p.font.name = font_name
        p.alignment = align
        return tf

    def add_card(slide, left, top, width, height, title, source, summary,
                 topics, url="", idx=0):
        from pptx.util import Emu
        # Card background
        shape = slide.shapes.add_shape(
            1, left, top, width, height
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = BG_CARD
        shape.line.fill.background()
        shape.shadow.inherit = False

        # Title
        add_textbox(slide, left + Emu(150000), top + Emu(80000),
                    width - Emu(300000), Emu(500000),
                    title, size=13, bold=True, color=WHITE)

        # Source + topics
        topic_colors_str = " | ".join(
            f"[{t}]" for t in topics if t != "general"
        ) if topics else ""
        meta = f"{source}" + (f"  {topic_colors_str}" if topic_colors_str else "")
        add_textbox(slide, left + Emu(150000), top + Emu(550000),
                    width - Emu(300000), Emu(300000),
                    meta, size=9, color=ACCENT)

        # Summary
        if summary:
            add_textbox(slide, left + Emu(150000), top + Emu(800000),
                        width - Emu(300000), Emu(500000),
                        summary[:200], size=10, color=GRAY)

    # ── Slide 1: Title ────────────────────────────────────────────────────
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    add_bg(slide)
    add_textbox(slide, Inches(1), Inches(2), Inches(11), Inches(1.5),
                "🤖  AI News Digest", size=44, bold=True, color=WHITE,
                align=PP_ALIGN.CENTER)
    add_textbox(slide, Inches(1), Inches(3.5), Inches(11), Inches(1),
                date_range, size=22, color=ACCENT,
                align=PP_ALIGN.CENTER)

    # Stats
    src_count = len(set(a.get("source", "?") for a in articles))
    topic_counts = Counter()
    for a in articles:
        for t in extract_topics(a.get("title", ""), a.get("summary", "")):
            topic_counts[t] += 1
    stats = f"{len(articles)} articles  |  {src_count} sources  |  {len(topic_counts)} topics"
    add_textbox(slide, Inches(1), Inches(4.5), Inches(11), Inches(0.8),
                stats, size=16, color=GRAY, align=PP_ALIGN.CENTER)

    # ── Slide 2: Topic Overview ──────────────────────────────────────────
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_textbox(slide, Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                "Topics Overview", size=28, bold=True, color=WHITE)

    TOPIC_LABELS = {
        "llm": "LLMs & Foundation Models",
        "ai_agent": "AI Agents",
        "ai_hardware": "AI Hardware (GPUs/Chips)",
        "robotics": "Robotics & Autonomous",
        "ai_healthcare": "AI in Healthcare",
        "ai_finance": "AI in Finance",
        "ai_images_video": "Image & Video Generation",
        "ai_code": "AI Coding Tools",
    }

    y = Inches(1.5)
    for topic, count in topic_counts.most_common(10):
        label = TOPIC_LABELS.get(topic, topic)
        bar_w = int(Inches(8) * (count / max(topic_counts.values(), default=1)))
        color = TOPIC_COLORS.get(topic, ACCENT)

        add_textbox(slide, Inches(0.5), y, Inches(4), Inches(0.4),
                    label, size=12, color=WHITE)
        add_textbox(slide, Inches(4.5), y, Inches(1), Inches(0.4),
                    str(count), size=12, color=ACCENT)

        # Bar
        shape = slide.shapes.add_shape(1, Inches(5.5), y + Emu(50000),
                                       Emu(bar_w), Inches(0.3))
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()

        y += Inches(0.5)
        if y > Inches(7):
            break

    # ── Source breakdown ─────────────────────────────────────────────────
    y2 = Inches(1.5)
    add_textbox(slide, Inches(9), Inches(0.3), Inches(4), Inches(0.8),
                "Sources", size=28, bold=True, color=WHITE)
    src_counts = Counter(a.get("source", "?") for a in articles)
    for src, cnt in src_counts.most_common(10):
        add_textbox(slide, Inches(9), y2, Inches(4), Inches(0.35),
                    f"{src}: {cnt}", size=10, color=GRAY)
        y2 += Inches(0.35)

    # ── Article Slides ───────────────────────────────────────────────────
    ARTICLES_PER_SLIDE = 6
    for batch_start in range(0, len(articles), ARTICLES_PER_SLIDE):
        batch = articles[batch_start:batch_start + ARTICLES_PER_SLIDE]
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        add_bg(slide)

        page = (batch_start // ARTICLES_PER_SLIDE) + 1
        total = (len(articles) + ARTICLES_PER_SLIDE - 1) // ARTICLES_PER_SLIDE
        add_textbox(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.5),
                    f"AI News  ({page}/{total})", size=18, bold=True, color=ACCENT)

        cols, rows = 3, 2
        card_w = Inches(4.0)
        card_h = Inches(3.2)
        gap_x = Inches(0.2)
        gap_y = Inches(0.2)
        start_x = Inches(0.3)
        start_y = Inches(0.7)

        for i, article in enumerate(batch):
            col = i % cols
            row = i // cols
            x = start_x + col * (card_w + gap_x)
            y = start_y + row * (card_h + gap_y)
            add_card(
                slide, x, y, card_w, card_h,
                article.get("title", "")[:80],
                article.get("source", "?"),
                article.get("summary", ""),
                extract_topics(article.get("title", ""), article.get("summary", "")),
                article.get("url", ""),
                i,
            )

    # ── Last Slide: Sources ──────────────────────────────────────────────
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_textbox(slide, Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                "Sources & Links", size=28, bold=True, color=WHITE)

    y = Inches(1.5)
    src_articles = defaultdict(list)
    for a in articles:
        src_articles[a.get("source", "?")].append(a)

    for src, arts in sorted(src_articles.items(), key=lambda x: -len(x[1])):
        if y > Inches(6.5):
            break
        txt = f"{src} ({len(arts)} articles)"
        add_textbox(slide, Inches(0.5), y, Inches(12), Inches(0.35),
                    txt, size=12, bold=True, color=ACCENT)
        y += Inches(0.35)
        for a in arts[:3]:
            title = a.get("title", "")[:70]
            url = a.get("url", "")
            add_textbox(slide, Inches(0.8), y, Inches(11), Inches(0.3),
                        f"- {title}", size=9, color=GRAY)
            y += Inches(0.25)
        y += Inches(0.15)

    prs.save(out_path)
    return out_path


def generate_markdown(articles: list[dict], date_range: str) -> str:
    from ai_news_scraper import extract_topics

    lines = []
    lines.append(f"# 🤖 AI News Digest\n")
    lines.append(f"**{date_range}** | {len(articles)} articles\n")
    lines.append("---\n")

    # Summary
    topic_counts = Counter()
    for a in articles:
        for t in extract_topics(a.get("title", ""), a.get("summary", "")):
            topic_counts[t] += 1

    TOPIC_LABELS = {
        "llm": "LLMs & Foundation Models",
        "ai_agent": "AI Agents",
        "ai_hardware": "AI Hardware",
        "robotics": "Robotics",
        "ai_healthcare": "AI in Healthcare",
        "ai_finance": "AI in Finance",
        "ai_images_video": "Image & Video Gen",
        "ai_code": "AI Coding",
    }

    lines.append("## 📊 Summary\n")
    for topic, count in topic_counts.most_common():
        label = TOPIC_LABELS.get(topic, topic)
        bar = "█" * count + "░" * max(0, 20 - count)
        lines.append(f"- **{label}**: {count} articles  `{bar}`")
    lines.append("")

    src_counts = Counter(a.get("source", "?") for a in articles)
    lines.append("## 📡 Sources\n")
    for src, cnt in src_counts.most_common():
        lines.append(f"- **{src}**: {cnt} articles")
    lines.append("")

    # Articles grouped by topic
    lines.append("## 📰 All Articles\n")
    for i, a in enumerate(articles, 1):
        topics = extract_topics(a.get("title", ""), a.get("summary", ""))
        topic_badges = " ".join(f"`{t}`" for t in topics if t != "general")
        published = (a.get("published", "") or "")[:16]
        source = a.get("source", "?")
        summary = (a.get("summary", "") or "")[:300]

        lines.append(f"### {i}. {a['title']}")
        lines.append(f"**{source}** {published}")
        if topic_badges:
            lines.append(f"{topic_badges}")
        if summary:
            lines.append(f"\n> {summary}")
        lines.append(f"\n🔗 [Read more]({a['url']})\n")

    return "\n".join(lines)


def save_csv_report(articles: list[dict], path: str):
    from ai_news_scraper import extract_topics

    keys = ["title", "url", "published", "summary", "author", "source", "topics"]
    for a in articles:
        a["topics"] = "; ".join(extract_topics(a.get("title", ""), a.get("summary", "")))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(articles)


def main():
    ap = argparse.ArgumentParser(description="AI News Digest — generate reports")
    ap.add_argument("--mode", default="daily", choices=["daily", "weekly"],
                    help="Digest period (default: daily)")
    ap.add_argument("--format", default="all",
                    choices=["pptx", "md", "csv", "json", "all"],
                    help="Output format (default: all)")
    ap.add_argument("--outdir", default="reports",
                    help="Output directory (default: ./reports)")
    ap.add_argument("--sources", default=None,
                    help="Comma-separated sources (default: all)")
    ap.add_argument("--max", type=int, default=100,
                    help="Max articles (default: 100)")
    ap.add_argument("--lang-hint", default="",
                    help="Language hint (e.g. 'hindi', 'english')")
    args = ap.parse_args()

    outdir = os.path.join(PROJECT_DIR, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    if args.mode == "weekly":
        from datetime import timedelta
        week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        date_range = f"{week_start} to {date_str}"
    else:
        date_range = date_str

    sources = args.sources.split(",") if args.sources else None
    max_n = args.max

    print(f"[*] Fetching AI news...")
    articles = asyncio.run(
        fetch_news(sources_filter=sources, max_articles=max_n, headless=True)
    )

    if not articles:
        print("[!] No articles found.")
        return

    print(f"   Got {len(articles)} articles from "
          f"{len(set(a.get('source','?') for a in articles))} sources")

    # Print summary
    from ai_news_scraper import extract_topics as et
    tc = Counter()
    for a in articles:
        for t in et(a.get("title", ""), a.get("summary", "")):
            tc[t] += 1
    TOPIC_LABELS = {
        "llm": "LLMs", "ai_agent": "Agents", "ai_hardware": "Hardware",
        "robotics": "Robotics", "ai_healthcare": "Health",
        "ai_finance": "Finance", "ai_images_video": "Image/Video",
        "ai_code": "Coding",
    }
    print(f"\n  Topics:")
    for topic, count in tc.most_common():
        label = TOPIC_LABELS.get(topic, topic)
        print(f"    {label:>15}: {count}")

    base_name = f"ai_digest_{args.mode}_{date_str}"
    formats_to_gen = ["pptx", "md", "csv"] if args.format == "all" else [args.format]

    generated = []
    for fmt in formats_to_gen:
        out_path = os.path.join(outdir, f"{base_name}.{fmt}")
        if fmt == "pptx":
            generate_pptx(articles, out_path, date_range)
        elif fmt == "md":
            md = generate_markdown(articles, date_range)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md)
        elif fmt == "csv":
            save_csv_report(articles, out_path)
        elif fmt == "json":
            out_path = os.path.join(outdir, f"{base_name}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(articles, f, indent=2, ensure_ascii=False)
        generated.append(out_path)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"\n  [[OK]] {fmt.upper():5s} -> {out_path}  ({size_kb:.0f} KB)")

    print(f"\n{'='*50}")
    print(f"  Digest saved to: {outdir}")
    print(f"  Total articles:  {len(articles)}")
    print(f"  Formats:         {', '.join(formats_to_gen)}")
    print(f"{'='*50}")

    return generated


if __name__ == "__main__":
    main()
