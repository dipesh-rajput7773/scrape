# Qorvai Launch Plan
**Target: Private Beta → Public Launch → $2B**

---

## PHASE 1 — Fix Before ANY User Touches It
*Estimated: 3-5 days*

### 1.1 Hosting & Deployment
- [ ] Create account on **Railway.app** (railway.app — free tier available)
- [ ] Create `Procfile` in root:
  ```
  web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
  ```
- [ ] Create `railway.toml` in root:
  ```toml
  [build]
  builder = "nixpacks"

  [deploy]
  startCommand = "playwright install chromium && streamlit run app.py --server.port=$PORT --server.address=0.0.0.0"
  restartPolicyType = "on_failure"
  ```
- [ ] Set environment variables in Railway dashboard (same as .env):
  - `OPENAI_API_KEY`
  - `WEBSHARE_API_KEY` (optional but recommended)
  - `EMAIL_FROM` + `EMAIL_PASS`
- [ ] Deploy → get live URL like `https://qorvai.up.railway.app`
- [ ] Test: open URL in incognito → make sure app loads

### 1.2 Stripe Payments (Switch to Live Mode)
- [ ] Login to stripe.com dashboard
- [ ] Switch from **Test Mode → Live Mode** (toggle top-left)
- [ ] Create 3 products:
  - Starter: $29/month
  - Pro: $79/month  
  - Agency: $199/month
- [ ] Copy live payment links → update in `subscription.py`
- [ ] Test a real $1 payment to confirm it works
- [ ] Set up webhook to auto-activate license after payment:
  - Stripe Dashboard → Webhooks → Add endpoint
  - Endpoint URL: `https://yourapp.railway.app/webhook`
  - Event: `checkout.session.completed`

### 1.3 Install Missing Package on Deployment
- [ ] Confirm `requirements.txt` has these (already added):
  - `dnspython>=2.8.0`
  - `python-dotenv>=1.0.0`
- [ ] Run `pip install -r requirements.txt` locally once to verify no errors

### 1.4 Basic Error Handling (Users see friendly messages)
- [ ] In `app.py` Find Leads tab — wrap scraper calls in try/except
- [ ] When scraper returns 0 results show:
  ```
  "No results found. Possible reasons:
   1. Try a different niche or city
   2. Enable proxy in Settings tab
   3. Use --show mode to check for CAPTCHA"
  ```
- [ ] When OpenAI key missing and user clicks AI scoring:
  ```
  "OpenAI API key not set. Go to Settings → API Keys to add it."
  ```
- [ ] When email sending fails show exact reason (wrong password, Gmail blocked, etc.)

---

## PHASE 2 — Before Public Launch
*Estimated: 1-2 weeks after Phase 1*

### 2.1 Onboarding Wizard (First-time users)
- [ ] Detect if user is new (no leads in DB + no API key set)
- [ ] Show 3-step setup screen:
  ```
  Step 1: What service do you sell?
          [Web Design] [Digital Marketing] [AI Automation]
          [Real Estate] [Recruitment] [Other]

  Step 2: Which city are you targeting?
          [Dubai] [Toronto] [Sydney] [London] [Custom...]

  Step 3: Add OpenAI API key (for AI scoring + emails)
          [sk-... text input]
          "Don't have one? Get free at platform.openai.com"

  → [Start Finding Leads]
  ```
- [ ] After setup: auto-run first scrape in background
- [ ] Show "Your first 10 leads are being found..." loading screen

### 2.2 Email Verification (Zero Bounce Guarantee)
- [ ] Sign up at **NeverBounce.com** (API, ~$0.003/verification)
- [ ] Add `NEVERBOUNCE_API_KEY` to `.env`
- [ ] In `email_finder.py` — after finding email, verify it:
  ```python
  import requests
  def verify_email(email: str) -> bool:
      key = os.getenv("NEVERBOUNCE_API_KEY", "")
      if not key:
          return True  # skip if no key
      r = requests.get(
          "https://api.neverbounce.com/v4/single/check",
          params={"key": key, "email": email}
      )
      result = r.json().get("result", "")
      return result in ("valid", "catchall")
  ```
- [ ] Only show verified emails to users
- [ ] Add "✅ Verified" badge next to emails in Database tab

### 2.3 Follow-up Email Sequences
- [ ] In Outreach tab — add "Create Sequence" button per lead
- [ ] Sequence structure:
  ```
  Day 0  → First email (already built)
  Day 3  → Follow-up #1: "Just bumping this up..."
  Day 7  → Follow-up #2: "Quick question about [pain point]"
  Day 14 → Break-up: "Closing your file — let me know if timing changes"
  ```
- [ ] Store sequence schedule in `leads.db`:
  ```sql
  ALTER TABLE leads ADD COLUMN sequence_step INTEGER DEFAULT 0;
  ALTER TABLE leads ADD COLUMN next_followup_at TEXT;
  ```
- [ ] Add "Scheduled" tab in Outreach showing pending follow-ups
- [ ] Manual "Send Now" button per follow-up

### 2.4 Need Score System (Pain Signal Detection)
- [ ] Create `need_scorer.py`:
  - Input: business data (name, website, reviews, rating, niche)
  - Output: need_score (0-100) + specific signals detected
- [ ] Signals to detect per niche:
  ```
  Web Agency targets:
    +50 if no website on Google Maps
    +30 if website loads >5 seconds (check via requests timing)
    +20 if no SSL (http:// URL)

  Automation targets:
    +35 if job posting found: "receptionist", "data entry"
    +25 if reviews mention: "slow response", "hard to reach"
    +20 if no chatbot on website

  Social Media targets:
    +30 if last Google post >90 days ago
    +25 if Instagram last post >60 days ago
    +20 if competitor active but they're not
  ```
- [ ] Show Need Score in Database tab as colored badge:
  - 70+ = 🔴 High Need
  - 40-70 = 🟡 Medium Need
  - <40 = 🟢 Low Need
- [ ] Filter by Need Score in Database tab

### 2.5 Multi-Community Support
- [ ] Add these niche categories to `niche_sources.py` (if not already):
  - [ ] Social Media Agency
  - [ ] IT Company / MSP
  - [ ] n8n Automation Freelancer
  - [ ] Real Estate Broker
  - [ ] Insurance Broker
  - [ ] E-commerce Consultant
  - [ ] Video Production Agency
  - [ ] Copywriting Agency
- [ ] For each niche: add correct sources + keywords + pain signals
- [ ] Test each niche returns at least 20 leads from at least 2 sources

---

## PHASE 3 — Growth & Moat Building
*Start immediately — runs parallel to Phase 1 & 2*

### 3.1 Background Data Collection (Start Day 1)
- [ ] Create `background_scraper.py` that runs on a schedule:
  ```
  Cities:  Dubai, Toronto, Sydney, London, New York, Mumbai,
           Singapore, Riyadh, Lagos, Nairobi (global coverage)
  Niches:  All 20 niches in niche_sources.py
  Schedule: 2 cities × 3 niches per hour = 6 combos/hour
            = 144 combos/day = complete refresh every 3 days
  ```
- [ ] Run this on Railway as a background worker (separate process)
- [ ] All results go to `master_businesses.db`
- [ ] After 30 days: 200,000+ businesses pre-scraped
- [ ] After 90 days: 1,000,000+ businesses = instant results for any search

### 3.2 Chrome Extension (Key Moat Feature)
- [ ] Create `chrome_extension/` folder in repo
- [ ] manifest.json — Chrome Extension v3
- [ ] Features:
  - User browses any website → button appears → "Save to Qorvai"
  - Auto-extracts: business name, email, phone, website
  - Sends to Qorvai API → saved to master DB
  - Shows "Already in your leads" if duplicate
- [ ] Publish to Chrome Web Store (one-time $5 fee)
- [ ] This makes Qorvai part of users' daily workflow = high retention

### 3.3 White Label System
- [ ] Add white label settings in admin panel:
  - Custom logo upload
  - Custom app name
  - Custom color scheme
  - Custom domain support
- [ ] White label pricing: $299-499/month
- [ ] Target: digital marketing agencies who want to resell to their clients
- [ ] First 5 white label partners = $1,500-2,500/month recurring

### 3.4 API Access (Developer Tier)
- [ ] Create REST API endpoints:
  ```
  GET  /api/leads?niche=dentist&city=Dubai&limit=50
  POST /api/scrape  { niche, city, sources }
  GET  /api/status/{job_id}
  ```
- [ ] API key management in Settings tab
- [ ] Rate limiting per plan tier
- [ ] Documentation page (simple markdown)
- [ ] Pricing: $199/month for API access
- [ ] Target: developers who want to integrate lead gen into their own tools

---

## PHASE 4 — Metrics to Hit Before Fundraising
*3-6 months*

### Revenue Milestones
- [ ] Month 1: 10 paying users → $500 MRR
- [ ] Month 2: 50 paying users → $2,500 MRR
- [ ] Month 3: 150 paying users → $8,000 MRR
- [ ] Month 6: 500 paying users → $30,000 MRR
- [ ] Month 12: 2,000 paying users → $120,000 MRR → raise Series A

### Data Milestones (Moat)
- [ ] 30 days: 500,000 businesses in master DB
- [ ] 90 days: 5,000,000 businesses in master DB
- [ ] 180 days: 20,000,000 businesses in master DB
- [ ] 1 year: 50,000,000 businesses — Apollo competitor territory

### Community Infiltration (free marketing)
- [ ] Post in r/n8n — "Free lead gen tool for automation freelancers"
- [ ] Post in r/digital_marketing — "How I find 200 clients/month"
- [ ] n8n official Discord — share in #showcase channel
- [ ] Facebook Groups: "Digital Marketing Agencies", "Web Design Business"
- [ ] LinkedIn posts: case studies of users who closed deals
- [ ] YouTube: 1 video showing tool in action → organic traffic

---

## QUICK WINS (Do These Today)

```
Priority 1 → Deploy on Railway (30 min)
             App goes from localhost → live URL
             You can share with anyone

Priority 2 → Test all scrapers manually
             Run: python maps_scraper.py "dentist" "Dubai" --max 10
             Run: python yelp_scraper.py "gym" "Toronto" --max 10
             Fix anything that errors

Priority 3 → Start background scraper
             Even 2 hours of scraping = 500+ businesses stored
             Data moat starts building from Day 1

Priority 4 → Join 3 communities and watch
             Don't post yet — just observe what problems people have
             That = free market research
```

---

## Files That Need To Be Built (Not Built Yet)

| File | What It Does | Priority |
|------|-------------|----------|
| `Procfile` | Railway deployment config | CRITICAL |
| `railway.toml` | Railway build config | CRITICAL |
| `need_scorer.py` | Pain signal detection (0-100 score) | HIGH |
| `background_scraper.py` | Auto-scrape cities/niches on schedule | HIGH |
| `email_verifier.py` | NeverBounce integration | HIGH |
| `followup_scheduler.py` | Day 0/3/7/14 sequence manager | MEDIUM |
| `chrome_extension/` | Browser extension folder | MEDIUM |
| `api_server.py` | REST API for developer tier | LOW |
| `onboarding.py` | First-time user setup wizard | HIGH |

---

## Current Stack Status

```
✅ DONE:
   maps_scraper.py       — Google Maps (stealth + proxy)
   yelp_scraper.py       — Yelp backup source
   clutch_scraper.py     — IT/Marketing agencies
   healthgrades_scraper.py — Medical/Dental
   tripadvisor_scraper.py  — Restaurants/Hotels
   email_finder.py       — Universal 5-step email pipeline
   linkedin_email.py     — LinkedIn → domain → email
   dork_email.py         — DuckDuckGo dorking
   master_db.py          — Data flywheel database
   proxy_manager.py      — Built-in proxy rotation
   niche_sources.py      — 20 niches × 7 sources routing
   leads_db.py           — User leads database
   enrich.py             — Website enrichment
   lead_scorer.py        — GPT scoring
   cold_email_gen.py     — AI email writer
   app.py                — Full Streamlit UI
   admin_db.py           — License management
   subscription.py       — Plan tiers
   stealth.py            — Anti-detection

🔲 TODO:
   Procfile + railway.toml  — Deployment
   need_scorer.py           — Pain signals
   background_scraper.py    — Auto data collection
   onboarding.py            — First-time flow
   followup_scheduler.py    — Email sequences
   email_verifier.py        — NeverBounce
   chrome_extension/        — Browser extension
```

---

## Revenue Projection

```
Month 1:  10 users × $49  = $490 MRR
Month 3:  100 users × $65 = $6,500 MRR
Month 6:  500 users × $75 = $37,500 MRR
Month 12: 2000 users × $79 = $158,000 MRR → $1.9M ARR
Month 24: 10,000 users + white label + API = $8M ARR
Month 36: 50,000 users + enterprise = $40M ARR
Exit/Series B: $400M-$2B valuation
```

---
*Last updated: 2026-05-19*
*Next review: After Phase 1 complete*
