from __future__ import annotations
"""
Generate niche-specific cold emails for enriched leads.
Works with both Meta Ads leads (enriched.csv) and Maps leads (maps_leads.csv).
Usage: python cold_email_gen.py input.csv output.csv [--niche realestate|dental|gym|salon|it|ecom]
Requires: OPENAI_API_KEY in env
"""

import csv
import os
import sys
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Niche prompts ─────────────────────────────────────────────────────────────

PROMPTS = {
    "realestate": """\
You write short cold emails for Qorvai — an AI automation agency.
Our service: WhatsApp AI agent that auto-follows up every new lead within 90 seconds, 24/7,
books viewings, sends property brochures, and qualifies buyers — without any human effort.

Lead:
- Agent/Agency: {name}
- Location: {location}
- About their company: {about}

Write a cold email:
Subject: one compelling line (specific, not generic)
Body (5-6 lines, under 90 words):
1. Hyper-personalized opener: Mention something specific from their "About" text to show we actually researched them.
2. Pain: agents lose 60-70% of leads because they respond too slow
3. Our fix: WhatsApp AI agent replies in <90 sec, 24/7, qualifies + books viewings automatically
4. Proof: "Agents using this convert 2-3x more leads without hiring staff"
5. CTA: "Worth a 15-min call this week?"

Tone: peer-to-peer, direct, no "Hope this finds you well".
Output format — first line is subject, blank line, then body.""",

    "dental": """\
Cold email for Qorvai — AI automation agency.
Our service: WhatsApp bot that auto-confirms appointments, sends reminders, handles reschedules,
and follows up post-treatment — cutting no-shows by up to 60%.

Lead:
- Clinic: {name}
- Location: {location}
- Phone: {phone}

Write a cold email:
Subject + body (5 lines, under 80 words):
1. Opener specific to dental practice
2. Pain: no-shows and manual reminder calls waste staff time and cost revenue
3. Fix: WhatsApp bot that auto-sends reminders 48h+2h before, lets patients reschedule instantly
4. Proof: "Clinics using this cut no-shows by 60% in the first month"
5. CTA: 15-min call or quick demo

No fluff. Professional tone.
Output: first line subject, blank line, body.""",

    "gym": """\
Cold email for Qorvai — AI automation agency.
Our service: WhatsApp AI agent that follows up every lead from ads within 2 min,
sends class schedules, handles membership queries, and auto-sends renewal offers.

Lead:
- Gym/Studio: {name}
- Location: {location}
- Phone: {phone}

Email (Subject + 5 lines, under 80 words):
1. Opener specific to fitness/gym
2. Pain: leads from Instagram/Facebook ads go cold because no one follows up fast
3. Fix: WhatsApp AI replies in 2 min, sends schedule, books trial class, follows up 3 days later
4. Proof: "Gyms using this see 35%+ more lead-to-member conversions"
5. CTA: quick call or send Loom

Direct, no fluff.
Output: subject line first, blank line, body.""",

    "salon": """\
Cold email for Qorvai — AI automation agency.
Our service: WhatsApp AI that handles appointment bookings, sends reminders,
promotes offers to past clients, and re-engages clients who haven't visited in 30+ days.

Lead:
- Salon/Spa: {name}
- Location: {location}
- Phone: {phone}

Email (Subject + 5 lines, under 80 words):
1. Opener specific to salon/beauty
2. Pain: missed bookings and no follow-up with old clients = lost revenue
3. Fix: WhatsApp bot takes bookings 24/7, reminds clients, sends "we miss you" offers automatically
4. Proof: "Salons using this fill 20% more weekly slots"
5. CTA: 15-min call

Friendly but direct tone.
Output: subject line, blank line, body.""",

    "it": """\
Cold email for Qorvai — AI automation agency.
Our service: n8n workflow automation + AI agents that automate client onboarding,
ticket routing, report generation, and internal ops — saving 15-20 hrs/week.

Lead:
- Company: {name}
- Location: {location}
- Has website: {has_website}

Email (Subject + 5 lines, under 90 words):
1. Opener about IT services / MSP space
2. Pain: repetitive internal tasks (tickets, onboarding, reports) eat engineering time
3. Fix: custom n8n automations + AI agents that handle these end-to-end
4. Proof: "IT firms using this save 15-20 hrs/week and reduce onboarding time by 50%"
5. CTA: 20-min discovery call

Professional, peer-to-peer tone.
Output: subject first, blank line, body.""",

    "it_outsource": """\
Cold email from a software outsourcing / staff augmentation partner reaching out to an IT company.
We offer: dedicated offshore dev teams (full-stack, mobile, AI/ML, DevOps) at 40-60% lower cost
than local hiring, with zero recruitment overhead and instant scale-up.

Lead:
- IT Company: {name}
- Location: {location}
- Has website: {has_website}

Write a SHORT, direct cold email (Subject + 5 lines, under 90 words):
1. Opener specific to the IT company — acknowledge they build software or manage tech projects
2. Pain: scaling dev capacity fast is expensive and slow with local hiring
3. Our offer: dedicated offshore dev team (same timezone overlap, English-fluent, vetted engineers) —
   ready to start in 1 week, 40-60% cost saving vs US/UK rates
4. Proof: "Companies like yours cut time-to-hire from 8 weeks to 5 days with our model"
5. CTA: "Can I send over a 2-min overview and a sample team profile?"

Tone: peer-to-peer, confident, no fluff, no "Hope this finds you well".
Output format — first line is subject (no "Subject:" prefix), blank line, then body.""",

    "ecom": """\
Cold email for Qorvai — AI automation agency.
Our service: WhatsApp AI that recovers abandoned carts, sends order updates,
handles FAQs, and runs re-engagement campaigns — boosting revenue 15-25%.

Lead:
- Store: {name}
- Location: {location}
- Has website: {has_website}
- Ad copy hint: {ad_copy}

Email (Subject + 5 lines, under 85 words):
1. Opener referencing their product/niche from ad copy
2. Pain: 70% of carts abandoned, email recovery rates are falling
3. Fix: WhatsApp AI that auto-messages within 15 min of abandonment with a personal note
4. Proof: "Stores using this recover 18-25% of abandoned carts"
5. CTA: 15-min call or free audit

Direct, conversion-focused tone.
Output: subject, blank line, body.""",

    "general": """\
Cold email for Qorvai — an AI automation agency.
Our services: WhatsApp AI chatbots, lead follow-up automation, appointment booking bots,
workflow automation (n8n), voice agents.

Lead:
- Business: {name}
- Location: {location}
- Has website: {has_website}

Email (Subject + 5 lines, under 85 words):
1. Opener specific to their business type
2. Pain point (lead follow-up / customer service / manual ops)
3. WhatsApp AI or workflow solution that fixes it
4. One result/proof line
5. Soft CTA: 15-min call

Professional, direct, no fluff.
Output: subject line first, blank line, body.""",
}

# ── Niche auto-detection ──────────────────────────────────────────────────────

NICHE_KEYWORDS = {
    "realestate": ["real estate", "property", "realty", "realtor", "homes for sale",
                   "mortgage", "letting", "estate agent"],
    "dental":     ["dental", "dentist", "clinic", "medical", "health", "doctor",
                   "physio", "orthodon", "teeth"],
    "gym":        ["gym", "fitness", "crossfit", "yoga", "pilates", "personal train",
                   "workout", "bootcamp"],
    "salon":      ["salon", "spa", "beauty", "hair", "nails", "barber", "aesthet"],
    "it":         ["it services", "managed services", "software", "tech support",
                   "msp", "cloud", "cybersec", "devops"],
    "ecom":       ["shopify", "ecommerce", "e-commerce", "online store", "dropship",
                   "merchandise", "amazon seller"],
}


def detect_niche(row: dict) -> str:
    text = " ".join([
        row.get("business_name", ""),
        row.get("page_name", ""),
        row.get("address", ""),
        row.get("ad_copy", ""),
    ]).lower()
    for niche, keywords in NICHE_KEYWORDS.items():
        if any(k in text for k in keywords):
            return niche
    return "general"


# ── Email generation ──────────────────────────────────────────────────────────

def generate_email(row: dict, force_niche: str | None = None):
    niche = force_niche or detect_niche(row)
    template = PROMPTS.get(niche, PROMPTS["general"])

    name     = row.get("business_name") or row.get("page_name") or "your business"
    location = (row.get("address") or row.get("location") or "your area")[:120]
    phone    = row.get("phone") or ""
    website  = row.get("website") or row.get("cta_url") or ""
    has_web  = "yes" if website else "no"
    ad_copy  = row.get("ad_copy", "")[:200]

    prompt = template.format(
        name=name, location=location, phone=phone,
        has_website=has_web, ad_copy=ad_copy,
        about=row.get("about_text", "N/A"),
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        raw = resp.choices[0].message.content.strip()
        lines = raw.splitlines()

        subject = ""
        body_lines = []
        for line in lines:
            if line.lower().startswith("subject:") and not subject:
                subject = line.split(":", 1)[1].strip()
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()

        return subject, body, niche
    except Exception as e:
        return "", f"[error: {e}]", niche


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Usage: python cold_email_gen.py input.csv output.csv [--niche NICHE]")
        print("Niches: realestate | dental | gym | salon | it | ecom | general")
        sys.exit(1)

    inp, out = sys.argv[1], sys.argv[2]
    force_niche = None
    if "--niche" in sys.argv:
        idx = sys.argv.index("--niche")
        if idx + 1 < len(sys.argv):
            force_niche = sys.argv[idx + 1]

    with open(inp, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"[*] Generating emails for {len(rows)} leads...")
    for i, row in enumerate(rows, 1):
        label = (row.get("business_name") or row.get("page_name") or f"Lead {i}")[:50]
        print(f"[{i}/{len(rows)}] {label}")
        subject, body, niche = generate_email(row, force_niche)
        row["email_subject"] = subject
        row["email_body"]    = body
        row["niche"]         = niche

    keys = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"[[OK]] Done -> {out}")


if __name__ == "__main__":
    main()
