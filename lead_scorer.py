"""
Lead Scorer + Pain Point Analyzer
Uses GPT to analyze each lead, identify their pain point, score them 0-100,
and classify as hot/warm/cold. Updates the leads database.

Usage:
    python lead_scorer.py enriched_maps_dubai.csv          # score a CSV
    python lead_scorer.py --from-db --temp cold --limit 50 # score DB leads
Requires: OPENAI_API_KEY
"""

import argparse
import csv
import json
import os
import sys
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCORE_PROMPT = """\
You are a lead qualification expert for Qorvai — an AI automation agency.
Services: WhatsApp AI agents, lead follow-up bots, appointment automation, n8n workflows, voice agents.
Ideal client: pays $1000-$5000/month, has a sales/booking problem, runs a real business.

Lead info:
- Business: {name}
- Location: {location}
- Source: {source}
- Phone: {phone}
- Email: {email}
- Website: {website}
- Bio/Post: {bio}
- Niche: {niche}

Score this lead and return ONLY valid JSON (no markdown, no extra text):
{{
  "score": <0-100 integer>,
  "temperature": "<hot|warm|cold>",
  "pain_point": "<1-2 sentence specific pain point this business likely has>",
  "pitch_angle": "<best automation service to pitch them and why, 1 sentence>",
  "reason": "<why you gave this score, 1 sentence>"
}}

Scoring guide:
- 80-100 (hot):  has email + phone, active business, clear automation pain, $1000+ budget likely
- 50-79  (warm): has email OR phone, real business, automation need exists
- 0-49   (cold): missing contact info, unclear business, low budget signals

Be specific about the pain point — use their location, niche, and any bio/post details."""


def score_lead(row: dict) -> dict:
    name    = row.get("business_name") or row.get("name") or "Unknown"
    bio     = (row.get("bio") or row.get("pain_point") or row.get("ad_copy") or "")[:400]
    website = row.get("website") or row.get("cta_url") or ""

    prompt = SCORE_PROMPT.format(
        name     = name,
        location = (row.get("address") or row.get("location") or "")[:100],
        source   = row.get("source", "unknown"),
        phone    = row.get("phone", ""),
        email    = row.get("email", ""),
        website  = website[:80],
        bio      = bio,
        niche    = row.get("niche", "realestate"),
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=250,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = raw.strip("` \n")
        if raw.startswith("json"):
            raw = raw[4:].strip()
        data = json.loads(raw)
        return {
            "score":       int(data.get("score", 0)),
            "temperature": data.get("temperature", "cold"),
            "pain_point":  data.get("pain_point", ""),
            "pitch_angle": data.get("pitch_angle", ""),
            "score_reason":data.get("reason", ""),
        }
    except Exception as e:
        return {"score": 0, "temperature": "cold", "pain_point": "", "pitch_angle": "", "score_reason": str(e)}


def score_csv(inp: str, out: str):
    with open(inp, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"[*] Scoring {len(rows)} leads with GPT...")
    hot, warm, cold = 0, 0, 0

    for i, row in enumerate(rows, 1):
        name = (row.get("business_name") or row.get("name") or f"Lead {i}")[:45]
        result = score_lead(row)
        row.update(result)
        t = result["temperature"]
        if t == "hot":   hot  += 1
        elif t == "warm": warm += 1
        else:             cold += 1
        print(f"  [{i}/{len(rows)}] {name:<45} score={result['score']:3d}  {t.upper()}")

    # Sort: hot first, then by score desc
    rows.sort(key=lambda r: (-{"hot":3,"warm":2,"cold":1}.get(r.get("temperature","cold"),0),
                              -int(r.get("score",0) or 0)))

    keys = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    print(f"\n[[OK]] Scored -> {out}")
    print(f"       HOT: {hot}  WARM: {warm}  COLD: {cold}")
    return rows


def score_db_leads(temperature_filter: str = None, limit: int = 50):
    """Score unscored leads directly from the database."""
    from leads_db import LeadsDB
    db = LeadsDB()

    with db._conn() as conn:
        q = "SELECT * FROM leads WHERE (score=0 OR score IS NULL) AND outreach_sent=0"
        if temperature_filter:
            q += f" AND temperature='{temperature_filter}'"
        q += f" LIMIT {limit}"
        conn.row_factory = __import__("sqlite3").Row
        rows = [dict(r) for r in conn.execute(q).fetchall()]

    if not rows:
        print("[!] No unscored leads in DB")
        return

    print(f"[*] Scoring {len(rows)} leads from DB...")
    for i, row in enumerate(rows, 1):
        name = (row.get("business_name") or "")[:45]
        result = score_lead(row)
        db.update_score(
            row["id"], result["score"], result["temperature"],
            result["pain_point"],
            row.get("email_subject", ""),
            row.get("email_body", ""),
        )
        print(f"  [{i}/{len(rows)}] {name:<45} {result['score']:3d}  {result['temperature'].upper()}")

    print(f"[[OK]] Done scoring DB leads")


def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("csv_file",  nargs="?", help="Input CSV to score")
    grp.add_argument("--from-db", action="store_true", help="Score leads from database")
    ap.add_argument("--out",    default=None,   help="Output CSV (default: scored_<input>)")
    ap.add_argument("--temp",   default=None,   help="Filter by temperature (with --from-db)")
    ap.add_argument("--limit",  type=int, default=50, help="Limit (with --from-db)")
    args = ap.parse_args()

    if args.from_db:
        score_db_leads(args.temp, args.limit)
    else:
        out = args.out or f"scored_{os.path.basename(args.csv_file)}"
        score_csv(args.csv_file, out)


if __name__ == "__main__":
    main()
