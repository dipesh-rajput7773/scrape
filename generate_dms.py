"""
Generate personalized cold DMs/emails for each enriched lead.
Usage: python generate_dms.py enriched.csv outreach.csv
Requires: OPENAI_API_KEY in env
"""

import csv
import os
import sys
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPT = """You write short, casual Instagram cold DMs for Qorvai — an AI automation agency.
Stack: WhatsApp AI agents, voice agents, lead automation, n8n workflows.

Lead info:
- Business: {page_name}
- Their ad copy: {ad_copy}
- Platform: {platforms}

Write a 4-line DM in this exact structure:
1. Specific compliment about their ad/business (mention one detail from ad copy)
2. Pain point question (related to leads/DMs/follow-up)
3. One-line offer (AI agent that solves it, ref a similar result)
4. Soft CTA (ask permission to send 2-min Loom)

Tone: peer-to-peer, no emojis, no "Hope you're doing well", under 60 words total.
Output ONLY the DM text, nothing else."""


def generate(row):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": PROMPT.format(
                    page_name=row.get("page_name", ""),
                    ad_copy=row.get("ad_copy", "")[:300],
                    platforms=row.get("platforms", ""),
                ),
            }],
            temperature=0.7,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"[error: {e}]"


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_dms.py enriched.csv outreach.csv")
        sys.exit(1)

    inp, out = sys.argv[1], sys.argv[2]
    with open(inp, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row.get('page_name','')[:40]}")
        row["dm"] = generate(row)

    keys = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"[[OK]] Done -> {out}")


if __name__ == "__main__":
    main()
