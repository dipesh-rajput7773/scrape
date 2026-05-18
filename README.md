# Qorvai — AI Agency Lead & Outreach Engine

Scrape leads → enrich with contact info → generate niche cold emails → auto-send.

## Setup (one time)

```bash
pip install -r requirements.txt
playwright install chromium
export OPENAI_API_KEY="sk-..."
```

---

## One-command pipeline

```bash
python run_pipeline.py --niche realestate --location "Dubai" --max 50
```

That single command runs all 3 steps automatically.

### Options

| Flag | Values | Description |
|------|--------|-------------|
| `--niche` | realestate, dental, gym, salon, it, ecom | Target industry |
| `--location` | "Dubai", "London", "New York", "Miami"... | Target city |
| `--max` | number | How many leads to collect |
| `--source` | maps, meta, both | Where to scrape from |
| `--send` | flag | Auto-send emails (needs Gmail creds) |
| `--show` | flag | Show browser window for debugging |

### Examples

```bash
# Real estate agents in Dubai (Google Maps)
python run_pipeline.py --niche realestate --location "Dubai" --max 60

# Dental clinics in London (Meta Ads)
python run_pipeline.py --niche dental --location "London" --max 50 --source meta

# Gyms in New York from both sources
python run_pipeline.py --niche gym --location "New York" --max 80 --source both

# IT companies in USA + auto send emails
python run_pipeline.py --niche it --location "USA" --max 50 --send
```

---

## Individual scripts

### 1. Google Maps Scraper
```bash
python maps_scraper.py "real estate agent" "Dubai" --max 50 --show
python maps_scraper.py "dental clinic" "London" --max 40
python maps_scraper.py "gym" "New York" --max 60
```
Output: `maps_leads.csv`

### 2. Meta Ads Scraper
```bash
python scraper.py "real estate" --country AE --max 100
python scraper.py "dental clinic" --country GB --max 100
python scraper.py "gym fitness" --country US --max 100
```
Country codes: US, GB, AE (Dubai), MA (Morocco), CA, AU, IN
Output: `leads.csv`

### 3. Enrich — extract email/phone/IG from websites
```bash
python enrich.py leads.csv enriched.csv
python enrich.py maps_leads.csv maps_enriched.csv
```

### 4. Generate cold emails (niche-specific GPT)
```bash
python cold_email_gen.py enriched.csv outreach.csv --niche realestate
python cold_email_gen.py enriched.csv outreach.csv --niche dental
python cold_email_gen.py enriched.csv outreach.csv --niche gym
```
Niches: `realestate | dental | gym | salon | it | ecom | general`

### 5. Send emails
```bash
# Set creds once
export EMAIL_FROM="you@gmail.com"
export EMAIL_PASS="your_app_password"   # NOT your real password

python email_sender.py outreach.csv
python email_sender.py outreach.csv --limit 40 --delay 90
```
Get Gmail App Password: https://myaccount.google.com/apppasswords

---

## Target markets for $1000+ clients

| Niche | Best Locations | Why they pay $1000+ |
|-------|---------------|---------------------|
| Real Estate | Dubai, London, New York, Miami | One deal = $5k-50k commission |
| Dental/Medical | US, UK | Appointment bot pays for itself in week 1 |
| Gym/Fitness | Dubai, London | Ad leads go cold — bot fixes this |
| IT Services | US, UK | Saves 15-20 hrs/week = immediate ROI |
| E-commerce | US, UK | Cart recovery = direct revenue |
| Salon/Spa | Dubai, London | Booking bot fills empty slots |

---

## Lead sources comparison

| Source | Best for | Volume | Quality |
|--------|----------|--------|---------|
| Google Maps | Local businesses (gym, salon, dental, restaurant) | High | High — has phone + address |
| Meta Ads Library | Businesses already spending on ads | Medium | Highest — they have budget |
| Both (`--source both`) | Maximum coverage | Highest | Mixed |

---

## Daily workflow (scale to 500+ leads/day)

```bash
# Morning run — Dubai real estate
python run_pipeline.py --niche realestate --location "Dubai" --max 100 --source both

# Afternoon run — London dental
python run_pipeline.py --niche dental --location "London" --max 100 --source both

# Evening — send all outreach
python email_sender.py outreach_realestate_dubai.csv --limit 40
python email_sender.py outreach_dental_london.csv    --limit 40
```

---

## Tips

- Run `--show` first time to confirm scraper works
- Gmail limit: ~500 emails/day. Use 40/hour to stay safe.
- Use Instantly.ai or Smartlead for bulk cold email at scale (>200/day)
- If Meta blocks: use mobile hotspot / different IP
- Maps scraper works best with `--show` to handle Google captchas manually

## File flow

```
maps_scraper.py  ──┐
                   ├──► leads.csv ──► enrich.py ──► enriched.csv ──► cold_email_gen.py ──► outreach.csv ──► email_sender.py
scraper.py       ──┘
```
