from __future__ import annotations
"""
Qorvai AI — Lead Gen & AI News Dashboard
Run: streamlit run app.py

Tabs:
  🔍 Find Leads  – Country, niche, pain point extraction, dedup
  📰 AI News     – 15+ sources, filter by keyword/country/topic
  📄 Digest      – Generate daily/weekly PPT/MD report
  💾 Database    – View, search, export leads
  📊 Dashboard   – Stats overview
  ⚙️ Settings    – API keys, email config
"""

import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from io import StringIO

import pandas as pd
import streamlit as st

from subscription import (
    get_subscription, set_subscription, is_pro, is_pro_plus, get_plan_features,
    get_leads_limit, activate_license, deactivate, get_plan_name,
    get_stripe_checkout_url, PLAN_FEATURES_LIST, PLANS,
)

# ── Add project root to path ─────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ── Load .env file (persisted API keys) ──────────────────────────────────
_ENV_FILE = os.path.join(PROJECT_DIR, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE, override=False)
except Exception:
    pass


def _save_env(updates: dict):
    """Save key=value pairs to .env file so they persist across restarts."""
    # Read existing lines
    existing: dict[str, str] = {}
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()
    # Merge updates (only non-empty values)
    for k, v in updates.items():
        if v:
            existing[k] = v
            os.environ[k] = v
    # Write back
    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")


# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="Qorvai AI — Intelligent Lead Engine", layout="wide", page_icon="⚡")

# ── Premium SaaS CSS (Linear/Stripe inspired) ────────────────────────────
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@500;600;700;800&display=swap');

    :root {
        --font-sans: 'Inter', -apple-system, sans-serif;
        --font-display: 'Outfit', 'Inter', sans-serif;
        --bg: #fafbfc;
        --bg-card: #ffffff;
        --bg-sidebar: #0f1119;
        --text: #0d0d12;
        --text-secondary: #6b7280;
        --text-tertiary: #9ca3af;
        --border: #e5e7eb;
        --border-light: #f3f4f6;
        --accent: #6366f1;
        --accent-light: #818cf8;
        --accent-dark: #4f46e5;
        --accent-glow: rgba(99,102,241,0.2);
        --gradient-1: #6366f1;
        --gradient-2: #8b5cf6;
        --gradient-3: #06b6d4;
        --green: #10b981;
        --amber: #f59e0b;
        --red: #ef4444;
        --radius: 12px;
        --radius-lg: 16px;
        --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
        --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        --shadow-md: 0 4px 6px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.04);
        --shadow-lg: 0 10px 25px rgba(0,0,0,0.06), 0 4px 10px rgba(0,0,0,0.04);
    }

    body.dark-mode {
        --bg: #0a0a10;
        --bg-card: rgba(255,255,255,0.04);
        --bg-sidebar: #0c0c14;
        --text: #f1f5f9;
        --text-secondary: #94a3b8;
        --text-tertiary: #64748b;
        --border: rgba(255,255,255,0.08);
        --border-light: rgba(255,255,255,0.04);
        --shadow-sm: 0 1px 2px rgba(0,0,0,0.2);
        --shadow: 0 1px 3px rgba(0,0,0,0.3);
        --shadow-md: 0 4px 6px rgba(0,0,0,0.3);
        --shadow-lg: 0 10px 25px rgba(0,0,0,0.4);
        --accent: #818cf8;
        --accent-glow: rgba(129,140,248,0.15);
    }

    html, body, [data-testid="stAppViewContainer"] {
        font-family: var(--font-sans);
        background: var(--bg);
        color: var(--text);
        transition: background 0.3s ease, color 0.3s ease;
    }
    [data-testid="stHeader"] { background: transparent !important; display: none !important; }

    [data-testid="stSidebar"] {
        background: var(--bg-sidebar) !important;
        border-right: 1px solid rgba(255,255,255,0.06) !important;
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] .stButton>button {
        background: rgba(255,255,255,0.06) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
    }
    [data-testid="stSidebar"] .stButton>button:hover {
        background: rgba(255,255,255,0.1) !important;
    }

    .sidebar-brand {
        font-family: var(--font-display);
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(135deg, var(--gradient-1), var(--gradient-2), var(--gradient-3));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .sidebar-tagline {
        color: #94a3b8 !important;
        font-size: 0.8rem;
        font-weight: 500;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }

    .nav-item {
        padding: 0.65rem 1rem;
        border-radius: 8px;
        font-size: 0.9rem;
        font-weight: 500;
        color: #94a3b8 !important;
        transition: all 0.15s ease;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .nav-item:hover, .nav-item.active {
        background: rgba(255,255,255,0.06);
        color: #f1f5f9 !important;
    }

    .main-header {
        font-family: var(--font-display);
        font-size: 2.5rem;
        font-weight: 800;
        letter-spacing: -1px;
        color: var(--text);
        margin-bottom: 0.15rem;
        animation: slideUp 0.5s ease-out;
    }
    .sub-header {
        font-size: 1rem;
        color: var(--text-secondary);
        font-weight: 400;
        margin-bottom: 2rem;
        animation: slideUp 0.5s ease-out 0.1s both;
    }

    .stat-card {
        background: var(--bg-card);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-radius: var(--radius-lg);
        padding: 1.5rem;
        border: 1px solid var(--border);
        box-shadow: var(--shadow);
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    .stat-card::after {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--gradient-1), var(--gradient-2), var(--gradient-3));
        opacity: 0;
        transition: opacity 0.25s ease;
    }
    .stat-card:hover {
        transform: translateY(-4px);
        box-shadow: var(--shadow-lg);
        border-color: var(--accent);
    }
    .stat-card:hover::after { opacity: 1; }

    .stat-number {
        font-family: var(--font-display);
        font-size: 2.2rem;
        font-weight: 800;
        color: var(--text);
        line-height: 1.1;
    }
    .stat-label {
        font-size: 0.78rem;
        color: var(--text-secondary);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-top: 0.35rem;
    }

    .news-card {
        background: var(--bg-card);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: var(--shadow-sm);
        transition: all 0.2s ease;
    }
    .news-card:hover {
        border-color: var(--accent);
        box-shadow: var(--shadow-md);
        transform: translateY(-2px);
    }
    .news-title { font-size: 1.05rem; font-weight: 600; color: var(--text); }

    .badge {
        display: inline-flex; align-items: center; gap: 4px;
        background: rgba(99,102,241,0.1); color: var(--accent);
        padding: 0.2rem 0.7rem; border-radius: 6px; font-size: 0.72rem;
        font-weight: 600; letter-spacing: 0.3px;
    }
    .badge-pro {
        background: linear-gradient(135deg, var(--gradient-1), var(--gradient-3));
        color: #fff;
        box-shadow: 0 4px 12px var(--accent-glow);
    }
    .badge-free {
        background: rgba(148,163,184,0.15);
        color: #94a3b8;
    }

    .stButton>button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        background: var(--text) !important;
        color: var(--bg) !important;
        border: none !important;
        padding: 0.55rem 1.2rem !important;
        transition: all 0.2s ease !important;
        box-shadow: var(--shadow-sm) !important;
    }
    .stButton>button:hover {
        opacity: 0.85 !important;
        transform: translateY(-1px) !important;
        box-shadow: var(--shadow-md) !important;
    }

    body.dark-mode .stButton>button {
        background: linear-gradient(135deg, var(--gradient-1), var(--gradient-2)) !important;
        color: #fff !important;
    }

    button[data-baseweb="tab"] {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
    }

    [data-testid="stExpander"] {
        background: var(--bg-card) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border-radius: var(--radius-lg) !important;
        border: 1px solid var(--border) !important;
        box-shadow: var(--shadow) !important;
    }
    [data-testid="stExpander"] summary {
        font-weight: 600 !important;
    }

    [data-testid="stMetricValue"] {
        color: var(--accent) !important;
        font-weight: 700 !important;
    }

    .divider {
        height: 1px;
        background: var(--border);
        margin: 2rem 0;
    }

    .pricing-card {
        background: var(--bg-card);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 2.5rem 2rem;
        text-align: center;
        box-shadow: var(--shadow);
        transition: all 0.3s ease;
        position: relative;
    }
    .pricing-card:hover {
        transform: translateY(-6px);
        box-shadow: var(--shadow-lg);
        border-color: var(--accent);
    }
    .pricing-card.featured {
        border-color: var(--accent);
        box-shadow: 0 0 0 1px var(--accent), var(--shadow-lg);
        transform: scale(1.03);
    }
    .pricing-card.featured:hover { transform: scale(1.03) translateY(-6px); }
    .pricing-card .popular-badge {
        position: absolute;
        top: -12px; left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, var(--gradient-1), var(--gradient-2));
        color: #fff;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.3rem 1rem;
        border-radius: 20px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }

    .pricing-price {
        font-family: var(--font-display);
        font-size: 3rem;
        font-weight: 800;
        color: var(--text);
    }
    .pricing-price span {
        font-size: 1rem;
        font-weight: 500;
        color: var(--text-secondary);
    }
    .pricing-name {
        font-family: var(--font-display);
        font-size: 1.3rem;
        font-weight: 700;
        color: var(--text);
        margin-bottom: 0.5rem;
    }

    @keyframes slideUp {
        from { opacity: 0; transform: translateY(16px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }

    .animate-in { animation: slideUp 0.5s ease-out both; }
    .delay-1 { animation-delay: 0.1s; }
    .delay-2 { animation-delay: 0.2s; }
    .delay-3 { animation-delay: 0.3s; }
    .delay-4 { animation-delay: 0.4s; }
</style>
<script>
    const isDark = localStorage.getItem('qorvai_dark_mode') === 'true';
    if (isDark) document.body.classList.add('dark-mode');
</script>
""",
    unsafe_allow_html=True,
)

# ── Session state ────────────────────────────────────────────────────────
if "db" not in st.session_state:
    from leads_db import LeadsDB as _LDB
    st.session_state.db = _LDB()
if "master_db" not in st.session_state:
    from master_db import MasterDB as _MDB
    st.session_state.master_db = _MDB()
if "news_cache" not in st.session_state:
    st.session_state.news_cache = []
if "news_fetched_at" not in st.session_state:
    st.session_state.news_fetched_at = None
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

DB     = st.session_state.db
MDB    = st.session_state.master_db   # Master businesses flywheel

# ── Constants ────────────────────────────────────────────────────────────
NICHES = ["realestate", "dental", "gym", "salon", "it", "ecom"]
SOURCES = ["maps", "meta", "reddit", "linkedin", "instagram"]
COUNTRIES = {
    "UAE (Dubai)": "AE",
    "United Kingdom": "GB",
    "United States": "US",
    "India": "IN",
    "Canada": "CA",
    "Singapore": "SG",
    "Germany": "DE",
    "France": "FR",
    "Japan": "JP",
    "Australia": "AU",
}

META_COUNTRY_MAP = {
    "AE": "AE", "GB": "GB", "US": "US", "IN": "IN",
    "CA": "CA", "SG": "SG", "DE": "DE", "FR": "FR",
    "JP": "JP", "AU": "AU",
}

LOCATION_MAP = {
    "AE": "Dubai", "GB": "London", "US": "New York",
    "IN": "Mumbai", "CA": "Toronto", "SG": "Singapore",
    "DE": "Berlin", "FR": "Paris", "JP": "Tokyo", "AU": "Sydney",
}

# ── Helpers ──────────────────────────────────────────────────────────────


def run_scraper_script(script: str, args: list[str]) -> str:
    py = sys.executable
    cmd = [py, os.path.join(PROJECT_DIR, script)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        return "[!] Timed out"
    except Exception as e:
        return f"[!] Error: {e}"


def generate_ai_search_params(prompt: str) -> dict:
    """Uses OpenAI to convert a natural language prompt into search parameters."""
    import json
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for AI Magic Search")
        
    client = OpenAI(api_key=api_key)
    
    system_prompt = """
    You are an expert B2B lead generation strategist.
    The user will describe their product and target audience.
    Your job is to generate the optimal search parameters to find these leads using scraping tools.
    
    You must return a JSON object with the following keys:
    - "source": The best platform to scrape. Choose one of: "maps" (for local businesses like plumbers, restaurants), "reddit" (for online communities, specific software users), "linkedin" (for corporate roles, B2B services). Default to "maps" if unsure.
    - "niche": A single broad category word (e.g., "Plumbers", "Restaurants", "SaaS", "Marketing").
    - "location": A specific city and state/country (e.g., "New York, USA", "London, UK", "Global"). For reddit, use "Global".
    - "keywords": A list of 1-3 specific search phrases (e.g., ["commercial plumber", "pipe repair"], ["b2b saas founder"]).
    
    Example input: "I sell marketing services to local dentists in Texas"
    Example output: {"source": "maps", "niche": "Dentist", "location": "Texas, USA", "keywords": ["dentist", "dental clinic", "orthodontist"]}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        response_format={ "type": "json_object" }
    )
    
    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        raise ValueError(f"Failed to parse AI response: {e}")


def sync_to_hubspot(leads: list[dict], token: str) -> tuple[int, list[str]]:
    """Sync leads to HubSpot CRM using the API. Returns (synced_count, errors)."""
    import requests as _req
    synced = 0
    errors = []
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for lead in leads:
        try:
            email = lead.get("email", "").strip()
            if not email:
                continue
            properties = {
                "email": email,
                "firstname": (lead.get("business_name", "") or "").split()[0] if lead.get("business_name") else "",
                "company": lead.get("business_name", ""),
                "phone": lead.get("phone", ""),
                "website": lead.get("website") or lead.get("cta_url") or "",
                "city": lead.get("location", ""),
                "hs_lead_status": (lead.get("temperature", "") or "").upper(),
            }
            properties = {k: v for k, v in properties.items() if v}
            resp = _req.post(
                "https://api.hubapi.com/crm/v3/objects/contacts",
                json={"properties": properties},
                headers=headers,
                timeout=15,
            )
            if resp.status_code in (201, 200):
                synced += 1
            elif resp.status_code == 409:
                # Already exists — update instead
                existing_id = resp.json().get("id")
                if existing_id:
                    _req.patch(
                        f"https://api.hubapi.com/crm/v3/objects/contacts/{existing_id}",
                        json={"properties": properties},
                        headers=headers,
                        timeout=15,
                    )
                synced += 1
            else:
                errors.append(f"{email}: HTTP {resp.status_code}")
        except Exception as e:
            errors.append(f"{lead.get('email','?')}: {e}")
    return synced, errors


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 1, "", "[!] Timed out")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", f"[!] {e}")


def read_csv_to_df(path: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        return df
    except Exception:
        return None


def csv_string_to_df(csv_text: str) -> pd.DataFrame | None:
    try:
        return pd.read_csv(StringIO(csv_text))
    except Exception:
        return None





# ── Dashboard ────────────────────────────────────────────────────────────


def show_dashboard():
    st.markdown('<p class="main-header">📊 Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Qorvai AI — Lead & News Overview</p>', unsafe_allow_html=True)

    try:
        s = DB.stats()
    except Exception:
        s = {"total": 0, "hot": 0, "warm": 0, "cold": 0,
             "sent": 0, "with_email": 0, "with_phone": 0}

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-label">Total Leads</div>'
            f'<div class="stat-number">{s["total"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col2:
        hot_pct = round(s["hot"] / max(s["total"], 1) * 100)
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-label">Hot Leads</div>'
            f'<div class="stat-number">{s["hot"]} <span class="stat-trend-up">↑ {hot_pct}%</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-label">Warm Leads</div>'
            f'<div class="stat-number" style="color:var(--amber)">{s["warm"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-label">Cold Leads</div>'
            f'<div class="stat-number" style="color:var(--text-tertiary)">{s["cold"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col5:
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-label">Verified Emails</div>'
            f'<div class="stat-number" style="color:var(--secondary-accent)">{s["with_email"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 Lead Activity")
        try:
            with DB._conn() as conn:
                rows = conn.execute(
                    "SELECT date(created_at) as day, COUNT(*) as cnt "
                    "FROM leads GROUP BY day ORDER BY day DESC LIMIT 14"
                ).fetchall()
            if rows:
                df = pd.DataFrame(rows, columns=["day", "count"])
                df = df.sort_values("day")
                st.bar_chart(df.set_index("day")["count"])
            else:
                st.info("No leads yet. Go to **Find Leads** tab to start.")
        except Exception:
            st.info("Connect to DB to see activity chart.")

    with col2:
        st.subheader("📰 Recent AI News")
        news = st.session_state.news_cache
        if news:
            for a in news[:5]:
                st.markdown(
                    f'<div class="news-card">'
                    f'<div class="news-title">{a["title"][:80]}</div>'
                    f'<div class="news-meta">{a.get("source","?")} '
                    f'{"· " + a.get("published","")[:16] if a.get("published") else ""}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if st.button("🔄 Refresh News", key="dash_refresh"):
                st.rerun()
        else:
            st.info("No news cached. Go to **AI News** tab to fetch.")

    st.subheader("⚡ Quick Actions")
    ca, cb, cc = st.columns(3)
    with ca:
        if st.button("🔍 Find New Leads", use_container_width=True):
            st.session_state["nav"] = "Find Leads"
            st.rerun()
    with cb:
        if st.button("📰 Fetch AI News", use_container_width=True):
            st.session_state["nav"] = "AI News"
            st.rerun()
    with cc:
        if st.button("💾 View Database", use_container_width=True):
            st.session_state["nav"] = "Database"
            st.rerun()


# ── Find Leads ───────────────────────────────────────────────────────────


def show_lead_finder():
    st.markdown('<p class="main-header">🔍 Find Leads</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Scrape + enrich + score leads from multiple sources</p>',
        unsafe_allow_html=True,
    )

    if not is_pro():
        st.warning(
            "💎 **Free Plan** — Limited to **10 leads/run**, 2 sources. "
            "[Upgrade to Pro](/) for unlimited leads, all 6 sources, proxy rotation & hyper-personalization."
        )

    with st.expander("⚙️ Search Mode", expanded=True):
        search_mode = st.radio("Mode", ["✨ AI Magic Search (Zero-Prompt)", "🛠️ Manual Filters"], horizontal=True)
        
        if search_mode == "✨ AI Magic Search (Zero-Prompt)":
            ai_prompt = st.text_area(
                "Describe your product and ideal customer", 
                placeholder="e.g., 'I sell an AI scheduling assistant to busy dental clinics in California'",
                help="We'll automatically figure out the best platform, location, and keywords to search."
            )
            
            fetch_max = get_leads_limit()
            if fetch_max == -1: fetch_max = 1000
            elif not is_pro(): fetch_max = 10
            max_leads = st.slider(
                "🎯 Max Leads", min_value=1, max_value=fetch_max,
                value=min(10, fetch_max), step=5 if is_pro() else 1,
                disabled=not is_pro()
            )
            extract_pain = st.checkbox("🧠 Extract Pain Points (uses GPT)", value=True)
            show_browser = st.checkbox("👁️ Show Browser", value=False)
            
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                country_label = st.selectbox(
                    "🌍 Country", list(COUNTRIES.keys()), index=0
                )
                country_code = COUNTRIES[country_label]
            with col2:
                niche = st.selectbox("🏢 Niche", NICHES, index=0)
            with col3:
                source = st.selectbox(
                    "📡 Source",
                    SOURCES + ["all"],
                    index=0,
                    help="maps=Google Maps, meta=Facebook Ads, reddit=inbound leads",
                )
            with col4:
                fetch_max = get_leads_limit()
                if fetch_max == -1:
                    fetch_max = 1000
                elif not is_pro():
                    fetch_max = 10
                max_leads = st.slider(
                    "🎯 Max Leads", min_value=1, max_value=fetch_max,
                    value=min(10, fetch_max), step=5 if is_pro() else 1,
                    disabled=not is_pro(),
                    help="Free: 10 leads. Pro: 300. Agency: unlimited."
                )

            col1, col2 = st.columns(2)
            with col1:
                extract_pain = st.checkbox(
                    "🧠 Extract Pain Points (uses GPT)",
                    value=True,
                    help="Automatically score & extract pain points after scraping",
                )
            with col2:
                show_browser = st.checkbox(
                    "👁️ Show Browser", value=False, help="Debug: watch the scraper live"
                )

    if st.button("🚀 Start Scraping", type="primary", use_container_width=True):
        if search_mode == "✨ AI Magic Search (Zero-Prompt)" and not ai_prompt.strip():
            st.error("Please describe your product and ideal customer.")
            return
        progress_bar = st.progress(0, text="Initializing...")
        status_box = st.empty()

        # Resolve parameters
        ai_keywords = []
        if search_mode == "✨ AI Magic Search (Zero-Prompt)":
            progress_bar.progress(5, text="🤖 AI analyzing your request and generating search queries...")
            try:
                params = generate_ai_search_params(ai_prompt)
                source = params.get("source", "maps")
                niche = params.get("niche", "Business")
                location = params.get("location", "Global")
                ai_keywords = params.get("keywords", [niche])
                st.info(f"**AI Selected Strategy:** Scrape `{source}` for `{niche}` in `{location}` using keywords: {ai_keywords}")
            except Exception as e:
                st.error(f"AI Generation Failed: {e}. Please check your OpenAI API Key.")
                return
        else:
            location = LOCATION_MAP.get(country_code, country_label)

        tag = f"{niche}_{location.lower().replace(' ','_').replace(',', '')}"
        output_csv = f"leads_{tag}.csv"

        try:
            total_new = 0
            output_text = ""

            # ── Master DB cache check ────────────────────────────────────
            # If we already scraped this niche+city recently, serve from DB
            city_key  = location.lower().strip()
            niche_key = niche.lower().strip()
            if source == "maps" and MDB.is_fresh(city_key, niche_key, min_count=15):
                progress_bar.progress(30, text="Serving from Qorvai master database (instant)...")
                cached = MDB.query(city_key, niche_key, limit=max_leads)
                if cached:
                    from leads_db import LeadsDB
                    ldb = LeadsDB()
                    added, skipped = 0, 0
                    for biz in cached:
                        rid = ldb.insert(biz, niche=niche, location=location, source="master_db")
                        if rid:
                            added += 1
                        else:
                            skipped += 1
                    total_new = added
                    progress_bar.progress(100, text="Done!")
                    status_box.success(
                        f"⚡ {added} leads from Qorvai database "
                        f"({skipped} already in your leads) — no scraping needed"
                    )
                    st.success(f"Instant results! {total_new} new leads from master database.")
                    if cached:
                        df_cached = pd.DataFrame(cached[:20])
                        cols = [c for c in ["business_name","phone","email","website",
                                            "rating","address"] if c in df_cached.columns]
                        st.subheader("📋 Results (from Master Database)")
                        st.dataframe(df_cached[cols] if cols else df_cached, use_container_width=True)
                    return
            # ── End cache check — proceed with live scrape ───────────────

            progress_bar.progress(10, text=f"Running {source} scraper for {niche} in {location}...")

            if source == "maps":
                if search_mode == "✨ AI Magic Search (Zero-Prompt)" and ai_keywords:
                    keywords = ai_keywords
                else:
                    from run_pipeline import NICHE_KEYWORDS
                    keywords = NICHE_KEYWORDS.get(niche, [niche])
                
                all_files = []
                for kw in keywords:
                    out = f"tmp_{tag}_{kw.replace(' ','_')}.csv"
                    show_f = ["--show"] if show_browser else []
                    r = run_cmd(
                        [sys.executable, os.path.join(PROJECT_DIR, "maps_scraper.py"),
                         kw, location, "--max", str(max_leads // len(keywords)),
                         "--out", out] + show_f
                    )
                    output_text += r.stdout + "\n" + r.stderr
                    if os.path.exists(out):
                        all_files.append(out)
                if all_files:
                    from run_pipeline import merge_csvs
                    total = merge_csvs(all_files, output_csv)
                    status_box.info(f"Maps: {total} leads found")
                    # Clean up temporary files
                    for tmp_f in all_files:
                        try:
                            if os.path.exists(tmp_f):
                                os.remove(tmp_f)
                        except Exception:
                            pass

            elif source == "meta":
                country_m = META_COUNTRY_MAP.get(country_code, "US")
                show_f = ["--show"] if show_browser else []
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "scraper.py"),
                     niche, "--country", country_m, "--max", str(max_leads),
                     "--out", output_csv] + show_f
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "reddit":
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "reddit_scraper.py"),
                     "--niche", niche, "--max", str(max_leads), "--out", output_csv]
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "linkedin":
                show_f = ["--show"] if show_browser else []
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "linkedin_scraper.py"),
                     niche, location, "--max", str(max_leads), "--out", output_csv] + show_f
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "instagram":
                ig_user = os.getenv("IG_USER", st.session_state.get("ig_user", ""))
                ig_pass = os.getenv("IG_PASS", st.session_state.get("ig_pass", ""))
                show_f = ["--show"] if show_browser else []
                from run_pipeline import NICHE_IG_HASHTAGS
                hashtags = ",".join(NICHE_IG_HASHTAGS.get(niche, [niche]))
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "instagram_scraper.py"),
                     "--hashtags", hashtags, "--max", str(max_leads),
                     "--user", ig_user, "--pass", ig_pass,
                     "--out", output_csv] + show_f
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "clutch":
                from niche_sources import get_clutch_category
                clutch_cat = get_clutch_category(niche) or niche.lower().replace(" ", "-")
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "clutch_scraper.py"),
                     clutch_cat, "--location", location,
                     "--max", str(max_leads), "--out", output_csv]
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "healthgrades":
                from niche_sources import get_healthgrades_specialty
                specialty = get_healthgrades_specialty(niche) or niche.lower()
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "healthgrades_scraper.py"),
                     specialty, location, "--max", str(max_leads), "--out", output_csv]
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "tripadvisor":
                ta_cat = "restaurant" if "restaurant" in niche.lower() else "hotel"
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "tripadvisor_scraper.py"),
                     ta_cat, location, "--max", str(max_leads), "--out", output_csv]
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "yelp":
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "yelp_scraper.py"),
                     niche, location, "--max", str(max_leads), "--out", output_csv]
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "dork":
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "dork_email.py"),
                     "--niche", niche, "--city", location,
                     "--max", str(max_leads)]
                )
                output_text += r.stdout + "\n" + r.stderr

            elif source == "all":
                # Multi-source: run all best sources for this niche in sequence
                from niche_sources import get_sources, get_keywords
                sources_for_niche = get_sources(niche)
                all_tmp_files = []
                total_per_source = max(10, max_leads // len(sources_for_niche))

                for src in sources_for_niche:
                    if len(all_tmp_files) * total_per_source >= max_leads:
                        break
                    tmp_csv = f"tmp_{tag}_{src}.csv"
                    progress_bar.progress(
                        15 + (sources_for_niche.index(src) * 10),
                        text=f"Scraping {src.upper()} for {niche} in {location}..."
                    )
                    try:
                        if src == "maps":
                            kws = get_keywords(niche, "maps")
                            for kw in kws[:2]:
                                kw_csv = f"tmp_{tag}_maps_{kw.replace(' ','_')}.csv"
                                run_cmd([sys.executable, os.path.join(PROJECT_DIR,"maps_scraper.py"),
                                         kw, location, "--max", str(total_per_source // len(kws[:2])),
                                         "--out", kw_csv])
                                if os.path.exists(kw_csv):
                                    all_tmp_files.append(kw_csv)
                        elif src == "yelp":
                            run_cmd([sys.executable, os.path.join(PROJECT_DIR,"yelp_scraper.py"),
                                     niche, location, "--max", str(total_per_source), "--out", tmp_csv])
                            if os.path.exists(tmp_csv): all_tmp_files.append(tmp_csv)
                        elif src == "clutch":
                            from niche_sources import get_clutch_category
                            cc = get_clutch_category(niche) or niche.lower().replace(" ","-")
                            run_cmd([sys.executable, os.path.join(PROJECT_DIR,"clutch_scraper.py"),
                                     cc, "--location", location, "--max", str(total_per_source), "--out", tmp_csv])
                            if os.path.exists(tmp_csv): all_tmp_files.append(tmp_csv)
                        elif src == "healthgrades":
                            from niche_sources import get_healthgrades_specialty
                            sp = get_healthgrades_specialty(niche) or niche.lower()
                            run_cmd([sys.executable, os.path.join(PROJECT_DIR,"healthgrades_scraper.py"),
                                     sp, location, "--max", str(total_per_source), "--out", tmp_csv])
                            if os.path.exists(tmp_csv): all_tmp_files.append(tmp_csv)
                        elif src == "tripadvisor":
                            tc = "restaurant" if "restaurant" in niche.lower() else "hotel"
                            run_cmd([sys.executable, os.path.join(PROJECT_DIR,"tripadvisor_scraper.py"),
                                     tc, location, "--max", str(total_per_source), "--out", tmp_csv])
                            if os.path.exists(tmp_csv): all_tmp_files.append(tmp_csv)
                        elif src == "dork":
                            run_cmd([sys.executable, os.path.join(PROJECT_DIR,"dork_email.py"),
                                     "--niche", niche, "--city", location, "--max", str(total_per_source)])
                        status_box.info(f"✅ {src.upper()} done")
                    except Exception as se:
                        output_text += f"\n[{src}] Error: {se}"

                # Merge all temp files
                if all_tmp_files:
                    from run_pipeline import merge_csvs
                    total = merge_csvs(all_tmp_files, output_csv)
                    for tf in all_tmp_files:
                        try: os.remove(tf)
                        except Exception: pass
                    status_box.info(f"🔀 Multi-source merge: {total} total leads")

            else:
                show_f = ["--show"] if show_browser else []
                r = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "run_pipeline.py"),
                     "--niche", niche, "--location", location,
                     "--source", "all", "--max", str(max_leads // 3)] + show_f
                )
                output_text += r.stdout + "\n" + r.stderr
                output_csv = f"leads_{niche}_{location.replace(' ','_').lower()}.csv"

            progress_bar.progress(60, text="Scraping done. Enriching leads...")

            enriched_csv = f"enriched_{tag}.csv"
            scored_csv = f"scored_{tag}.csv"

            if not os.path.exists(output_csv):
                status_box.error("No results found.")
                st.warning(
                    "**No leads found — here's what to try:**\n\n"
                    "1. 🔄 Try a **different niche or city** (e.g. 'dentist' → 'dental clinic')\n"
                    "2. 🌐 Enable **Proxy Rotation** in the Settings tab to bypass rate limits\n"
                    "3. 👁️ Enable **Show Browser** mode to check if a CAPTCHA is blocking the scraper\n"
                    "4. 📡 Try a different **source** (e.g. switch Maps → Yelp or Clutch)\n"
                    "5. ⏳ Wait 60 seconds and try again — Google Maps may have rate-limited you"
                )
            else:
                # Enrich
                r2 = run_cmd(
                    [sys.executable, os.path.join(PROJECT_DIR, "enrich.py"),
                     output_csv, enriched_csv]
                )
                output_text += r2.stdout + "\n" + r2.stderr
                progress_bar.progress(75, text="Enrichment done.")

                # Score + extract pain points
                has_scored = False
                if extract_pain:
                    _openai_key = os.getenv("OPENAI_API_KEY", "").strip()
                    if not _openai_key:
                        st.warning(
                            "⚠️ **OpenAI API key not set** — AI scoring skipped.\n\n"
                            "Go to **Settings → API Keys** to add your key, then re-run. "
                            "Get a free key at [platform.openai.com](https://platform.openai.com)."
                        )
                        extract_pain = False
                    else:
                        progress_bar.progress(85, text="Extracting pain points with GPT...")
                        if os.path.exists(enriched_csv):
                            r3 = run_cmd(
                                [sys.executable, os.path.join(PROJECT_DIR, "lead_scorer.py"),
                                 enriched_csv, "--out", scored_csv]
                            )
                            output_text += r3.stdout + "\n" + r3.stderr
                            has_scored = os.path.exists(scored_csv)

                # Import to DB
                progress_bar.progress(95, text="Importing to database...")
                from leads_db import LeadsDB
                ldb = LeadsDB()

                import_csv = scored_csv if has_scored else (enriched_csv if os.path.exists(enriched_csv) else "")
                if import_csv and os.path.exists(import_csv):
                    added, skipped = ldb.import_csv(
                        import_csv, niche=niche,
                        location=location, source=source
                    )
                    total_new = added
                    status_box.success(f"✅ {added} NEW leads added ({skipped} duplicates skipped)")

                    # ── Store into master businesses flywheel ────────────
                    try:
                        import csv as _csv
                        with open(import_csv, newline="", encoding="utf-8") as _f:
                            master_rows = list(_csv.DictReader(_f))
                        m_new, m_upd = MDB.bulk_upsert(master_rows, niche=niche, city=location)
                        st.caption(f"🗄️ Master DB: +{m_new} new businesses stored ({m_upd} updated)")
                    except Exception:
                        pass
                    # ── End master DB store ──────────────────────────────

                else:
                    status_box.warning("⚠️ No enriched data to import. Try --show to debug.")

            progress_bar.progress(100, text="Done!")
            st.success(f"Scraping complete! {total_new} new leads in database.")

            # Show results from DB (not from temp CSV files)
            if total_new > 0:
                try:
                    with DB._conn() as conn:
                        conn.row_factory = __import__("sqlite3").Row
                        rows = conn.execute(
                            "SELECT business_name, phone, email, website, "
                            "pain_point, score, temperature, source "
                            "FROM leads ORDER BY created_at DESC LIMIT 20"
                        ).fetchall()
                    if rows:
                        df_result = pd.DataFrame([dict(r) for r in rows])
                        st.subheader("📋 Latest Results (from Database)")
                        st.dataframe(df_result, use_container_width=True)
                        csv_dl = df_result.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "📥 Download CSV", csv_dl,
                            f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                            "text/csv", use_container_width=True,
                        )
                except Exception:
                    pass

            # Clean up intermediate CSV files — DB is the source of truth
            for tmp in [output_csv, enriched_csv, scored_csv]:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass

            with st.expander("📜 Scraper Log"):
                st.text(output_text[:5000])

        except Exception as e:
            err_str = str(e).lower()
            if "playwright" in err_str or "chromium" in err_str or "browser" in err_str:
                st.error(
                    "🌐 **Browser/Playwright Error** — Chromium is not installed or crashed.\n\n"
                    "Fix: Run `playwright install chromium` in your terminal, then try again."
                )
            elif "timeout" in err_str or "timed out" in err_str:
                st.error(
                    "⏱️ **Scraper Timed Out** — The target website is responding too slowly.\n\n"
                    "Try: Enable **Proxy Rotation** in Settings, or switch to a different source."
                )
            elif "openai" in err_str or "api key" in err_str or "authentication" in err_str:
                st.error(
                    "🔑 **OpenAI API Key Error** — Your key is missing or invalid.\n\n"
                    "Go to **Settings → API Keys** and add a valid key from "
                    "[platform.openai.com](https://platform.openai.com)."
                )
            elif "connection" in err_str or "network" in err_str or "ssl" in err_str:
                st.error(
                    "📡 **Network Error** — Could not connect to the target website.\n\n"
                    "Check your internet connection or try enabling a proxy in Settings."
                )
            else:
                st.error(f"❌ **Unexpected Error:** {e}")
            with st.expander("🔍 Technical Details (for debugging)"):
                import traceback
                st.code(traceback.format_exc(), language="python")

    # Recent scrapes
    st.divider()
    st.subheader("🕐 Recently Collected Leads")
    try:
        with DB._conn() as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = conn.execute(
                "SELECT business_name, phone, email, niche, location, "
                "source, pain_point, score, temperature, created_at "
                "FROM leads ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            df.columns = [c.replace("_", " ").title() for c in df.columns]
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No leads yet.")
    except Exception:
        st.info("Database not available.")


# ── AI News ──────────────────────────────────────────────────────────────


def show_ai_news():
    st.markdown('<p class="main-header">📰 AI News</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Latest AI updates from 15+ sources — Anthropic, '
        'OpenAI, NVIDIA, Product Hunt, TechCrunch, Reddit & more</p>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        keyword = st.text_input(
            "🔑 Keyword Filter",
            placeholder="e.g. Claude, NVIDIA, Sora...",
            help="Filter articles by keyword",
        )
    with col2:
        country_opts = ["All"] + list(COUNTRIES.keys())
        country_filter = st.selectbox("🌍 Country Filter", country_opts, index=0)
    with col3:
        max_articles = st.slider("📄 Max Articles", 10, 200, 50, 10)

    source_opts = [
        "All", "openai", "anthropic", "nvidia", "google_ai", "deepmind",
        "meta_ai", "techcrunch_ai", "venturebeat_ai", "mit_tech_review",
        "ars_technica_ai", "hackernews", "reddit_artificial",
        "reddit_machinelearning", "huggingface", "producthunt",
    ]
    selected_sources = st.multiselect(
        "📡 Sources", source_opts, default=["All"],
        help="Select specific sources (default: all)",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        fetch_btn = st.button(
            "🚀 Fetch News", type="primary", use_container_width=True
        )
    with col2:
        if st.session_state.news_fetched_at:
            st.caption(
                f"Last fetched: {st.session_state.news_fetched_at}"
                f" | {len(st.session_state.news_cache)} articles cached"
            )

    if fetch_btn:
        with st.spinner("Fetching AI news from all sources..."):
            sources_arg = None
            if "All" not in selected_sources and selected_sources:
                sources_arg = ",".join(selected_sources)

            country_code = ""
            if country_filter != "All":
                country_code = COUNTRIES[country_filter]

            out_csv = f"ai_news_temp_{datetime.now().strftime('%H%M%S')}.csv"
            cmd = [sys.executable, os.path.join(PROJECT_DIR, "ai_news_scraper.py"),
                   "--max", str(max_articles), "--output", out_csv]
            if sources_arg:
                cmd += ["--sources", sources_arg]
            if keyword:
                cmd += ["--keyword", keyword]
            if country_code:
                cmd += ["--country", country_code]

            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if os.path.exists(out_csv):
                    df = read_csv_to_df(out_csv)
                    if df is not None and not df.empty:
                        articles = df.to_dict("records")
                        st.session_state.news_cache = articles
                        st.session_state.news_fetched_at = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        st.success(f"Fetched {len(articles)} articles from "
                                   f"{len(set(a.get('source','') for a in articles))} sources")
                    os.remove(out_csv)
                else:
                    st.error(f"Scraper produced no output. Check logs below.")
                if r.stdout or r.stderr:
                    with st.expander("📜 Scraper Log"):
                        st.text((r.stdout + "\n" + r.stderr)[:4000])
            except subprocess.TimeoutExpired:
                st.error("Timed out after 180s. Some sources may be slow. Try fewer sources.")
            except Exception as e2:
                st.error(f"Failed: {e2}")

    news = st.session_state.news_cache

    if not news:
        st.info("No news fetched yet. Click **Fetch News** above.")
        return

    st.divider()

    # Topic filter
    all_topics = set()
    for a in news:
        from ai_news_scraper import extract_topics
        all_topics.update(extract_topics(a.get("title", ""), a.get("summary", "")))
    topic_list = ["All"] + sorted(all_topics)
    topic_filter = st.selectbox("🏷️ Topic Filter", topic_list, index=0)

    filtered = news
    if topic_filter != "All":
        from ai_news_scraper import extract_topics

        filtered = [
            a
            for a in filtered
            if topic_filter in extract_topics(a.get("title", ""), a.get("summary", ""))
        ]

    st.markdown(f"**{len(filtered)} articles**")

    # Stats
    from collections import Counter
    source_counts = Counter(a.get("source", "?") for a in filtered)
    st.markdown(
        " | ".join(f"**{s}:** {c}" for s, c in source_counts.most_common(8))
    )

    # Display as cards
    for i, a in enumerate(filtered):
        from ai_news_scraper import extract_topics
        topics = extract_topics(a.get("title", ""), a.get("summary", ""))
        topic_badges = " ".join(
            f'<span class="badge">{t}</span>' for t in topics if t != "general"
        )
        source = a.get("source", "?")
        published = (a.get("published", "") or "")[:16]
        summary = (a.get("summary", "") or "")[:250]
        title = a.get("title", "Untitled")
        url = a.get("url", "")

        st.markdown(
            f'<div class="news-card">'
            f'<div class="news-title"><a href="{url}" target="_blank">{title}</a></div>'
            f'<div class="news-meta">{source}'
            + (f" · {published}" if published else "")
            + f"</div>"
            + (f'<div class="news-summary">{summary}...</div>' if summary else "")
            + (f'<div style="margin-top:0.3rem">{topic_badges}</div>' if topic_badges else "")
            + f'</div>',
            unsafe_allow_html=True,
        )

    # Export
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if filtered:
            df = pd.DataFrame(filtered)
            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download CSV",
                csv_data,
                f"ai_news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True,
            )
    with col2:
        if filtered:
            json_data = json.dumps(filtered, indent=2, ensure_ascii=False).encode("utf-8")
            st.download_button(
                "📥 Download JSON",
                json_data,
                f"ai_news_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                "application/json",
                use_container_width=True,
            )


# ── Outreach ─────────────────────────────────────────────────────────────


def show_outreach():
    st.markdown('<p class="main-header">📧 Outreach</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Hyper-personalized emails — written from each lead\'s own website</p>',
        unsafe_allow_html=True,
    )

    if not is_pro():
        st.markdown(
            """
            <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:16px;
            padding:2rem;text-align:center;color:#fff;margin-bottom:1.5rem;">
            <div style="font-size:2rem;font-weight:800;margin-bottom:0.5rem;">🔒 Starter Feature</div>
            <div style="font-size:1rem;opacity:0.9;margin-bottom:1rem;">
            Hyper-personalized outreach is available on Starter ($29/mo) and above.<br>
            Each email is written using the lead's own About page — not a generic template.
            </div>
            <div style="font-size:0.85rem;opacity:0.75;">Upgrade to unlock 1-click send, GPT personalization & tracking</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("⚡ Upgrade to Starter — $29/mo", type="primary", use_container_width=True):
            st.session_state["nav"] = "Pricing"
            st.rerun()
        return

    # ── Filters ──────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        temp_f = st.selectbox("🌡️ Temperature", ["hot", "warm", "all"], index=0)
    with col2:
        niche_f = st.selectbox("🏢 Niche", ["All"] + NICHES, index=0)
    with col3:
        has_email_f = st.checkbox("Has email only", value=True)
    with col4:
        limit_f = st.slider("Max leads", 5, 50, 10)

    # ── Load leads ────────────────────────────────────────────────────────
    try:
        with DB._conn() as conn:
            conn.row_factory = __import__("sqlite3").Row
            q = "SELECT * FROM leads WHERE outreach_sent=0"
            params = []
            if temp_f != "all":
                q += " AND temperature=?"
                params.append(temp_f)
            if niche_f != "All":
                q += " AND niche=?"
                params.append(niche_f)
            if has_email_f:
                q += " AND email != '' AND email IS NOT NULL"
            q += " ORDER BY score DESC LIMIT ?"
            params.append(limit_f)
            rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    except Exception as e:
        st.error(f"DB error: {e}")
        return

    if not rows:
        st.info("No leads match filters. Try scraping more leads in **Find Leads** tab.")
        return

    # ── Guarantee banner ──────────────────────────────────────────────────
    plan_feat = get_plan_features()
    guarantee = plan_feat.get("guarantee", "")
    st.markdown(
        f'<div style="background:rgba(16,185,129,0.1);border:1px solid #10b981;border-radius:10px;'
        f'padding:0.75rem 1.25rem;margin-bottom:1rem;color:#10b981;font-weight:600;">'
        f'✅ {guarantee} — Emails written using each lead\'s own About page</div>',
        unsafe_allow_html=True,
    )

    st.markdown(f"**{len(rows)} leads ready for outreach**")

    # ── Per-lead email cards ──────────────────────────────────────────────
    email_from = os.getenv("EMAIL_FROM", "")
    email_pass = os.getenv("EMAIL_PASS", "")
    can_send = bool(email_from and email_pass)

    for i, lead in enumerate(rows):
        name = lead.get("business_name") or f"Lead {i+1}"
        temp = lead.get("temperature", "cold")
        score = lead.get("score", 0) or 0
        pain = lead.get("pain_point", "") or "Not extracted yet"
        email_addr = lead.get("email", "")
        phone = lead.get("phone", "")
        about = lead.get("about_text", "") or ""
        subj = lead.get("email_subject", "") or ""
        body = lead.get("email_body", "") or ""
        lead_id = lead.get("id")

        temp_color = {"hot": "#ef4444", "warm": "#f59e0b", "cold": "#6b7280"}.get(temp, "#6b7280")
        temp_emoji = {"hot": "🔥", "warm": "🌡️", "cold": "❄️"}.get(temp, "❄️")

        with st.expander(
            f"{temp_emoji} {name[:55]} — Score {score} | {email_addr[:35] or 'No email'}",
            expanded=(i == 0),
        ):
            col_l, col_r = st.columns([2, 3])

            with col_l:
                st.markdown(
                    f'<div class="stat-card">'
                    f'<div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;'
                    f'letter-spacing:1px;color:{temp_color};">{temp_emoji} {temp.upper()} LEAD</div>'
                    f'<div style="font-size:1.8rem;font-weight:800;margin:0.25rem 0;">{score}/100</div>'
                    f'<div style="font-size:0.82rem;color:var(--text-secondary);">AI Confidence Score</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("**📍 Contact Info**")
                if email_addr:
                    st.code(email_addr, language=None)
                if phone:
                    st.caption(f"📞 {phone}")
                st.markdown("**🧠 Pain Point**")
                st.info(pain[:200] if pain else "Run AI scoring to extract pain point")
                if about:
                    with st.expander("📄 About Page Snippet"):
                        st.caption(about[:500])

            with col_r:
                st.markdown("**✉️ Personalized Email**")

                # Generate email if not already there
                gen_key = f"gen_{lead_id}"
                if not subj and not body:
                    if st.button(f"🤖 Generate Email with AI", key=f"gen_btn_{i}", use_container_width=True):
                        with st.spinner("Writing personalized email from their About page..."):
                            try:
                                from cold_email_gen import generate_email
                                g_subj, g_body, g_niche = generate_email(lead)
                                # Update DB
                                with DB._conn() as conn:
                                    conn.execute(
                                        "UPDATE leads SET email_subject=?, email_body=? WHERE id=?",
                                        (g_subj, g_body, lead_id),
                                    )
                                    conn.commit()
                                subj, body = g_subj, g_body
                                st.success("✅ Email generated!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Generation failed: {e}")

                subj_edit = st.text_input(
                    "Subject", value=subj,
                    key=f"subj_{i}_{lead_id}",
                    placeholder="Click Generate Email first",
                )
                body_edit = st.text_area(
                    "Email Body", value=body,
                    key=f"body_{i}_{lead_id}",
                    height=180,
                    placeholder="Click Generate Email first",
                )

                col_send, col_mark = st.columns(2)
                with col_send:
                    if can_send and email_addr and subj_edit and body_edit:
                        if st.button(f"🚀 Send Email", key=f"send_{i}", type="primary", use_container_width=True):
                            try:
                                from email_sender import send_email
                                ok = send_email(email_addr, subj_edit, body_edit)
                                if ok:
                                    with DB._conn() as conn:
                                        conn.execute(
                                            "UPDATE leads SET outreach_sent=1 WHERE id=?",
                                            (lead_id,),
                                        )
                                        conn.commit()
                                    st.success(f"✅ Email sent to {email_addr}!")
                                    st.rerun()
                                else:
                                    st.error("Send failed. Check email settings.")
                            except Exception as e:
                                st.error(f"Error: {e}")
                    elif not can_send:
                        st.caption("⚙️ Set Gmail in Settings to send")
                    elif not email_addr:
                        st.caption("❌ No email for this lead")

                with col_mark:
                    if st.button("✓ Mark Sent", key=f"mark_{i}", use_container_width=True):
                        with DB._conn() as conn:
                            conn.execute("UPDATE leads SET outreach_sent=1 WHERE id=?", (lead_id,))
                            conn.commit()
                        st.success("Marked as sent!")
                        st.rerun()

    st.divider()
    # Bulk generate button
    if st.button("🤖 Generate Emails for ALL Leads Above", use_container_width=True):
        with st.spinner(f"Generating {len(rows)} personalized emails..."):
            from cold_email_gen import generate_email
            done = 0
            for lead in rows:
                if not lead.get("email_subject"):
                    try:
                        s, b, _ = generate_email(lead)
                        with DB._conn() as conn:
                            conn.execute(
                                "UPDATE leads SET email_subject=?, email_body=? WHERE id=?",
                                (s, b, lead.get("id")),
                            )
                            conn.commit()
                        done += 1
                    except Exception:
                        pass
            st.success(f"✅ Generated {done} personalized emails!")
            st.rerun()


# ── Database ─────────────────────────────────────────────────────────────


def show_database():
    st.markdown('<p class="main-header">💾 Database</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">View, search, filter, and export leads</p>',
        unsafe_allow_html=True,
    )

    try:
        s = DB.stats()
    except Exception:
        s = {}

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", s.get("total", 0))
    with col2:
        st.metric("Hot", s.get("hot", 0))
    with col3:
        st.metric("Warm", s.get("warm", 0))
    with col4:
        st.metric("Cold", s.get("cold", 0))

    # Filters
    with st.expander("🔍 Search & Filter", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            search = st.text_input("Search name/email/phone", "")
        with col2:
            temp_filter = st.selectbox(
                "Temperature",
                ["All", "hot", "warm", "cold"],
                index=0,
            )
        with col3:
            niche_filter = st.selectbox(
                "Niche", ["All"] + NICHES, index=0
            )
        with col4:
            has_email = st.checkbox("Has email only", value=False)

    # Query
    try:
        with DB._conn() as conn:
            conn.row_factory = __import__("sqlite3").Row
            q = "SELECT * FROM leads WHERE 1=1"
            params = []
            if temp_filter != "All":
                q += " AND temperature=?"
                params.append(temp_filter)
            if niche_filter != "All":
                q += " AND niche=?"
                params.append(niche_filter)
            if has_email:
                q += " AND email != ''"
            if search:
                q += " AND (business_name LIKE ? OR email LIKE ? OR phone LIKE ?)"
                s = f"%{search}%"
                params.extend([s, s, s])
            q += " ORDER BY created_at DESC LIMIT 500"
            rows = conn.execute(q, params).fetchall()

        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            # Drop internal columns
            drop_cols = [c for c in ["id", "phone_norm", "email_norm", "name_norm"]
                         if c in df.columns]
            df = df.drop(columns=drop_cols, errors="ignore")

            st.dataframe(df, use_container_width=True)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Export CSV",
                    csv_data,
                    f"leads_export_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv",
                    use_container_width=True,
                )
            with col2:
                st.metric("Displaying", f"{len(df)} leads")
            with col3:
                with_email = (df["email"] != "").sum() if "email" in df.columns else 0
                st.metric("With Email", with_email)
            with col4:
                hubspot_token = os.getenv("HUBSPOT_TOKEN", "")
                if hubspot_token:
                    if st.button("☁️ Sync to HubSpot", use_container_width=True):
                        leads_with_email = df[df["email"].notna() & (df["email"] != "")]
                        if leads_with_email.empty:
                            st.warning("No leads with email to sync.")
                        else:
                            leads_list = leads_with_email.to_dict("records")
                            synced, errors = sync_to_hubspot(leads_list, hubspot_token)
                            if synced:
                                st.success(f"✅ {synced} leads synced to HubSpot!")
                            if errors:
                                with st.expander(f"⚠️ {len(errors)} errors"):
                                    st.text("\n".join(errors[:20]))
                else:
                    st.caption("☁️ Set HubSpot token in Settings")
        else:
            st.info("No leads match the filters.")
    except Exception as e:
        st.error(f"Database error: {e}")

    st.divider()
    st.subheader("📥 Import CSV to Database")

    uploaded_file = st.file_uploader(
        "Upload a CSV file",
        type="csv",
        help="Upload leads CSV to import into database",
    )
    if uploaded_file is not None:
        try:
            df_import = pd.read_csv(uploaded_file)
            st.dataframe(df_import.head(10), use_container_width=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                imp_niche = st.selectbox("Niche for import", NICHES, index=0)
            with col2:
                imp_location = st.text_input("Location", placeholder="e.g. Dubai")
            with col3:
                imp_source = st.selectbox(
                    "Source", SOURCES + ["csv_import"], index=5
                )

            if st.button("📥 Import to Database", use_container_width=True):
                rows_list = df_import.to_dict("records")
                added, skipped = 0, 0
                for row in rows_list:
                    rid = DB.insert(
                        row, niche=imp_niche,
                        location=imp_location, source=imp_source
                    )
                    if rid:
                        added += 1
                    else:
                        skipped += 1
                st.success(f"✅ {added} new leads added, {skipped} duplicates skipped")
        except Exception as e:
            st.error(f"Import error: {e}")


# ── Settings ─────────────────────────────────────────────────────────────


def show_settings():
    st.markdown('<p class="main-header">⚙️ Settings</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Configure API keys and preferences</p>',
        unsafe_allow_html=True,
    )

    with st.expander("🔑 API Keys", expanded=True):
        openai_key = st.text_input(
            "OpenAI API Key",
            value=os.getenv("OPENAI_API_KEY", ""),
            type="password",
            help="Required for pain point extraction & email generation",
        )
        hubspot_key = st.text_input(
            "HubSpot Access Token (CRM)",
            value=os.getenv("HUBSPOT_TOKEN", ""),
            type="password",
            help="Used to sync leads to your CRM automatically. Get from HubSpot Settings > Integrations > Private Apps",
        )
        col_hs1, col_hs2 = st.columns([1, 4])
        with col_hs1:
            if hubspot_key and st.button("🔌 Test Connection", key="hs_test"):
                with st.spinner("Testing HubSpot connection..."):
                    import requests as _req
                    try:
                        r = _req.get(
                            "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
                            headers={"Authorization": f"Bearer {hubspot_key}", "Content-Type": "application/json"},
                            timeout=10,
                        )
                        if r.status_code == 200:
                            st.success("✅ HubSpot connection OK!")
                        else:
                            st.error(f"❌ Failed: HTTP {r.status_code} — {r.text[:200]}")
                    except Exception as e:
                        st.error(f"❌ Connection error: {e}")
        with col_hs2:
            st.caption("Test your HubSpot token before syncing leads.")
        if st.button("💾 Save API Keys", type="primary", use_container_width=True, key="save_keys"):
            _save_env({
                "OPENAI_API_KEY": openai_key,
                "HUBSPOT_TOKEN":  hubspot_key,
            })
            st.success("✅ Keys saved — will persist after restart")
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
        if hubspot_key:
            os.environ["HUBSPOT_TOKEN"]  = hubspot_key

    with st.expander("🌐 Anti-Ban Proxy Pool", expanded=True):
        st.markdown(
            "**Built-in rotating proxy system** — auto-fetches free proxies, "
            "tests them, and rotates IPs per session. Zero config needed."
        )

        # ── Live pool status ─────────────────────────────────────────────
        try:
            from proxy_manager import POOL
            s = POOL.status()

            tier_color = {"webshare": "🟢", "custom": "🟢", "free": "🟡", "none": "🔴"}
            tier_label = {"webshare": "Webshare (best)", "custom": "Custom", "free": "Free pool", "none": "Not started"}
            tier_icon  = tier_color.get(s["tier"], "⚪")
            tier_name  = tier_label.get(s["tier"], s["tier"])

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Working Proxies", s["pool_size"], help="IPs currently in rotation")
            with col2:
                st.metric("Tier", f"{tier_icon} {tier_name}")
            with col3:
                st.metric("Requests Proxied", s["requests_proxied"])
            with col4:
                age = s["last_refresh_min"]
                st.metric("Pool Age", f"{age}m" if age >= 0 else "Pending")

            if s["sample_proxies"]:
                masked = [p.split("@")[-1] if "@" in p else p[:25] + "..." for p in s["sample_proxies"]]
                st.caption(f"Sample active IPs: {' · '.join(masked)}")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🔄 Refresh Proxy Pool", use_container_width=True):
                    with st.spinner("Fetching and testing proxies..."):
                        POOL.force_refresh()
                    st.success(f"✅ Pool refreshed — {POOL.status()['pool_size']} proxies ready")
                    st.rerun()
            with col_btn2:
                st.caption(
                    "Auto-refreshes every 30 min. "
                    "Free proxies work for most sites. "
                    "Add Webshare key below for Google-grade proxies."
                )

        except Exception as ex:
            st.warning(f"Proxy pool not loaded yet: {ex}")

        st.divider()

        # ── Webshare free tier (best quality, 1-time signup) ─────────────
        st.markdown("##### Webshare Free Tier (Recommended)")
        st.caption(
            "Sign up free at webshare.io → API Keys → copy key here. "
            "Gives 10 rotating residential-quality proxies. Far better than raw free lists."
        )
        webshare_key = st.text_input(
            "Webshare API Key",
            value=os.getenv("WEBSHARE_API_KEY", ""),
            type="password",
            placeholder="Paste Webshare API key here",
        )
        if webshare_key:
            os.environ["WEBSHARE_API_KEY"] = webshare_key

        # ── Custom proxy override ─────────────────────────────────────────
        st.markdown("##### Custom Proxy (Optional Override)")
        st.caption("If you have a paid proxy (Smartproxy, Oxylabs, etc.), paste it here. Overrides all other sources.")
        proxy_url = st.text_input(
            "Proxy URL",
            value=os.getenv("PROXY_URL", ""),
            placeholder="http://user:pass@proxy.example.com:8080",
            help="Formats: http://, https://, socks5://",
        )
        if proxy_url:
            os.environ["PROXY_URL"] = proxy_url

        if st.button("💾 Save Proxy Settings", key="save_proxy"):
            _save_env({"WEBSHARE_API_KEY": webshare_key, "PROXY_URL": proxy_url})
            st.success("✅ Proxy settings saved")

        # ── Proxy tier guide ─────────────────────────────────────────────
        st.markdown("""
| Tier | Cost | Works on | Setup |
|------|------|----------|-------|
| 🟢 Custom paid proxy | $5-20/mo | Google Maps, everything | Paste URL above |
| 🟢 Webshare free | $0 | Yelp, most sites, partial Maps | 1-time signup |
| 🟡 Auto free pool | $0 | Yelp, local sites | None — auto |
| ⚪ No proxy (direct) | $0 | Light Maps scraping only | None |
        """)

    with st.expander("💎 Subscription & Billing", expanded=True):
        sub = get_subscription()
        plan_name = get_plan_name()
        plan_features = get_plan_features()

        col1, col2 = st.columns([3, 2])
        with col1:
            if is_pro():
                plan_label = plan_name
                plan_label += " (Agency)" if sub.get("plan") == "agency" else " (Pro)"
                st.success(f"✅ **{plan_label} Plan** — Active")
                expiry = sub.get("expires_at")
                if expiry:
                    remaining = max(0, int((expiry - time.time()) / 86400))
                    st.markdown(f"**{remaining} days** remaining in billing period")
                st.markdown(
                    "- ✅ Unlimited leads\n"
                    "- ✅ Proxy rotation\n"
                    "- ✅ Hyper-personalization\n"
                    "- ✅ CRM sync\n"
                    + ("- ✅ White-label\n" if sub.get("plan") == "agency" else "")
                )
                if sub.get("license_key"):
                    st.caption(f"License: {sub['license_key'][:12]}...")
                if st.button("↘️ Cancel Subscription", type="secondary", use_container_width=True):
                    deactivate()
                    st.rerun()
            else:
                st.info("You're on the **Free Plan**")
                st.markdown(
                    "- 10 leads per run\n"
                    "- 2 data sources\n"
                    "- Basic outreach only\n"
                    "- No proxy / CRM / personalization"
                )
                st.page_link("app.py", label="🚀 **See Pricing →**", use_container_width=True)

        with col2:
            st.markdown("##### Activate License")
            lic = st.text_input("License key", placeholder="XXXX-XXXX-XXXX", label_visibility="collapsed")
            if st.button("🔑 Activate", use_container_width=True, key="activate_lic"):
                success = activate_license(lic)
                if success:
                    st.success("✅ License activated!")
                    st.rerun()
                else:
                    st.error("❌ Invalid license key")
            st.divider()
            st.caption(
                "**[Purchase License](https://buy.stripe.com/test_8wE4jA3qX9vK3C4aEE)** "
                "— Instant activation after payment"
            )

    with st.expander("📧 Email Settings"):
        email_from = st.text_input(
            "Gmail Address",
            value=os.getenv("EMAIL_FROM", ""),
            placeholder="you@gmail.com",
        )
        email_pass = st.text_input(
            "Gmail App Password",
            value=os.getenv("EMAIL_PASS", ""),
            type="password",
            placeholder="16-character app password",
            help="Get from https://myaccount.google.com/apppasswords",
        )
        if email_from:
            os.environ["EMAIL_FROM"] = email_from
        if email_pass:
            os.environ["EMAIL_PASS"] = email_pass
        if st.button("💾 Save Email Settings", key="save_email"):
            _save_env({"EMAIL_FROM": email_from, "EMAIL_PASS": email_pass})
            st.success("✅ Email settings saved")

    with st.expander("📷 Instagram Login (optional)"):
        st.info("Instagram login is needed for hashtag scraping.")
        ig_user = st.text_input(
            "Instagram Username",
            value=os.getenv("IG_USER", st.session_state.get("ig_user", "")),
        )
        ig_pass = st.text_input(
            "Instagram Password",
            value=os.getenv("IG_PASS", ""),
            type="password",
        )
        if ig_user:
            st.session_state.ig_user = ig_user
            os.environ["IG_USER"] = ig_user
        if ig_pass:
            os.environ["IG_PASS"] = ig_pass
        if st.button("💾 Save Instagram Settings", key="save_ig"):
            _save_env({"IG_USER": ig_user, "IG_PASS": ig_pass})
            st.success("✅ Instagram settings saved")

    with st.expander("📊 Lead Scoring Config"):
        st.info(
            "Lead scoring uses GPT to analyze each lead and assign "
            "0-100 score + hot/warm/cold temperature."
        )
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Scoring Criteria:**")
            st.markdown("- **80-100 (Hot):** Has email + phone, active business, clear automation need")
            st.markdown("- **50-79 (Warm):** Has email/phone, real business, automation exists")
            st.markdown("- **0-49 (Cold):** Missing contact, unclear business")
        with col2:
            st.markdown("**Pain Points Extracted:**")
            st.markdown("- Lead follow-up automation")
            st.markdown("- Appointment booking")
            st.markdown("- Customer service / FAQ")
            st.markdown("- Workflow automation (n8n)")

    st.divider()
    st.subheader("📊 Leads Database Stats")
    try:
        s = DB.stats()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Leads", s["total"])
            st.metric("Outreach Sent", s["sent"])
        with col2:
            st.metric("With Email", s["with_email"])
            st.metric("With Phone", s["with_phone"])
        with col3:
            st.metric("Hot", s["hot"])
            st.metric("Warm", s["warm"])
        st.caption(f"Leads DB: {os.path.join(PROJECT_DIR, 'leads.db')}")
    except Exception as e:
        st.error(f"DB error: {e}")

    st.divider()
    st.subheader("🗄️ Master Businesses Database (Data Flywheel)")
    try:
        ms = MDB.stats()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Businesses", ms["total"])
        with col2:
            st.metric("With Email", ms["with_email"])
        with col3:
            st.metric("Cities Covered", ms["cities"])
        with col4:
            st.metric("Niches Covered", ms["niches"])

        coverage = MDB.coverage()
        if coverage:
            st.markdown("**Coverage by City + Niche:**")
            df_cov = pd.DataFrame(coverage)
            st.dataframe(df_cov, use_container_width=True, hide_index=True)
        st.caption(
            f"Master DB: {os.path.join(PROJECT_DIR, 'master_businesses.db')} — "
            "Every scrape feeds this database. Searches here first = instant results."
        )
    except Exception as e:
        st.error(f"Master DB error: {e}")

    st.divider()
    if st.button("🗑️ Clear Session Cache", use_container_width=True):
        st.session_state.news_cache = []
        st.session_state.news_fetched_at = None
        st.success("Cache cleared!")
        st.rerun()


# ── Digest ───────────────────────────────────────────────────────────────


def show_digest():
    st.markdown('<p class="main-header">📄 AI News Digest</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Generate daily/weekly AI news reports — PPT, Markdown, CSV</p>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        digest_mode = st.radio(
            "📅 Period",
            ["daily", "weekly"],
            index=0,
            horizontal=True,
            help="Daily = all recent news | Weekly = last 7 days",
        )
    with col2:
        digest_format = st.radio(
            "📄 Output Format",
            ["all", "pptx", "md", "csv", "json"],
            index=0,
            horizontal=True,
            help="Generate all formats or pick one",
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        digest_max = st.slider(
            "📰 Max Articles", 20, 200, 80, 10,
            help="More articles = bigger report",
        )
    with col2:
        digest_sources = st.text_input(
            "📡 Specific Sources (optional)",
            placeholder="e.g. openai,anthropic,nvidia",
            help="Comma-separated. Leave empty for all sources.",
        )
    with col3:
        digest_outdir = st.text_input(
            "📁 Output Folder", value="reports",
            help="Folder to save reports in",
        )

    if st.button("🚀 Generate Digest Report", type="primary", use_container_width=True):
        progress = st.progress(0, text="Fetching AI news...")
        status = st.empty()

        try:
            from ai_digest import (
                generate_pptx,
                generate_markdown,
                save_csv_report,
            )

            progress.progress(20, text="Fetching AI news from all sources...")

            digest_csv = f"digest_temp_{datetime.now().strftime('%H%M%S')}.csv"
            digest_cmd = [sys.executable, os.path.join(PROJECT_DIR, "ai_news_scraper.py"),
                          "--max", str(digest_max), "--output", digest_csv]
            if digest_sources:
                digest_cmd += ["--sources", digest_sources]

            r_digest = subprocess.run(digest_cmd, capture_output=True, text=True, timeout=180)
            articles = []
            if os.path.exists(digest_csv):
                df_digest = read_csv_to_df(digest_csv)
                if df_digest is not None and not df_digest.empty:
                    articles = df_digest.to_dict("records")
                os.remove(digest_csv)

            if not articles:
                status.error("No articles found. Try again later.")
                return

            progress.progress(50, text=f"Compiling {len(articles)} articles...")

            outdir = os.path.join(PROJECT_DIR, digest_outdir)
            os.makedirs(outdir, exist_ok=True)

            date_str = datetime.now().strftime("%Y-%m-%d")
            if digest_mode == "weekly":
                from datetime import timedelta

                ws = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                date_range = f"{ws} to {date_str}"
            else:
                date_range = date_str

            base = f"ai_digest_{digest_mode}_{date_str}"
            formats_to_gen = (
                ["pptx", "md", "csv"]
                if digest_format == "all"
                else [digest_format]
            )

            generated = []
            for i, fmt in enumerate(formats_to_gen):
                pct = 50 + (40 * (i + 1) // len(formats_to_gen))
                progress.progress(pct, text=f"Generating {fmt.upper()}...")

                out_path = os.path.join(outdir, f"{base}.{fmt}")
                if fmt == "pptx":
                    generate_pptx(articles, out_path, date_range)
                elif fmt == "md":
                    md = generate_markdown(articles, date_range)
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(md)
                elif fmt == "csv":
                    save_csv_report(articles, out_path)
                elif fmt == "json":
                    import json as _json
                    with open(out_path, "w", encoding="utf-8") as f:
                        _json.dump(articles, f, indent=2, ensure_ascii=False)
                generated.append(out_path)

            progress.progress(100, text="Done!")

            # Stats
            from ai_news_scraper import extract_topics
            from collections import Counter

            tc = Counter()
            for a in articles:
                for t in extract_topics(a.get("title", ""), a.get("summary", "")):
                    tc[t] += 1

            TOPIC_LABELS = {
                "llm": "LLMs", "ai_agent": "Agents", "ai_hardware": "Hardware",
                "robotics": "Robotics", "ai_healthcare": "Health",
                "ai_finance": "Finance", "ai_images_video": "Image/Video",
                "ai_code": "Coding",
            }

            st.success(f"✅ Digest generated! {len(articles)} articles from "
                       f"{len(set(a.get('source','') for a in articles))} sources")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📊 Topics Breakdown")
                for topic, count in tc.most_common():
                    label = TOPIC_LABELS.get(topic, topic)
                    st.markdown(f"- **{label}**: {count}")
            with col2:
                src_counts = Counter(a.get("source", "?") for a in articles)
                st.subheader("📡 Sources")
                for src, cnt in src_counts.most_common(10):
                    st.markdown(f"- **{src}**: {cnt}")

            st.divider()

            for path in generated:
                size_kb = os.path.getsize(path) / 1024
                fmt = path.split(".")[-1].upper()
                with open(path, "rb") as fh:
                    st.download_button(
                        f"📥 Download {fmt} ({size_kb:.0f} KB)",
                        fh,
                        os.path.basename(path),
                        "application/octet-stream",
                        use_container_width=True,
                    )

            st.info(f"Files saved to: `{os.path.abspath(outdir)}`")

        except Exception as e:
            status.error(f"Error: {e}")
            import traceback
            st.text(traceback.format_exc())

    st.divider()

    # Show existing reports
    reports_dir = os.path.join(PROJECT_DIR, "reports")
    if os.path.isdir(reports_dir):
        st.subheader("📁 Previous Reports")
        files = sorted(
            [f for f in os.listdir(reports_dir) if f.startswith("ai_digest")],
            reverse=True,
        )[:20]
        if files:
            for f in files:
                fpath = os.path.join(reports_dir, f)
                size = os.path.getsize(fpath) / 1024
                st.text(f"  {f}  ({size:.0f} KB)")
        else:
            st.info("No previous reports yet.")

    # Quick preview
    if st.session_state.news_cache:
        st.divider()
        st.subheader("👁️ Preview (cached news)")
        st.dataframe(
            pd.DataFrame([
                {"title": a["title"][:60], "source": a.get("source","")}
                for a in st.session_state.news_cache[:10]
            ]),
            use_container_width=True,
        )


# ── Pricing ──────────────────────────────────────────────────────────────


def show_pricing():
    st.markdown('<p class="main-header">⚡ Pricing</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Transparent pricing. Every plan comes with a verified contact guarantee.</p>',
        unsafe_allow_html=True,
    )

    current_plan = get_subscription().get("plan", "free")

    col1, col2, col3, col4 = st.columns(4)

    plans_data = [
        {
            "key": "free",
            "name": "Free",
            "price": "$0",
            "period": "forever",
            "desc": "Try before you buy",
            "guarantee": "Up to 10 verified contacts/run",
            "features": [
                "10 leads per run",
                "Google Maps only",
                "Email enrichment",
                "GPT pain point scoring",
                "Export to CSV",
            ],
            "featured": False,
        },
        {
            "key": "starter",
            "name": "Starter",
            "price": "$29",
            "period": "/month",
            "desc": "First real clients, fast",
            "guarantee": "50 verified contacts/month",
            "features": [
                "100 leads per run",
                "3 sources (Maps, Reddit, Meta)",
                "Hyper-personalized emails",
                "1-click outreach",
                "AI pain points + scoring",
            ],
            "featured": False,
            "popular": None,
        },
        {
            "key": "pro",
            "name": "Pro",
            "price": "$79",
            "period": "/month",
            "desc": "Scale your outreach",
            "guarantee": "300 verified contacts/month",
            "features": [
                "500 leads per run",
                "All 6 data sources",
                "Proxy rotation (anti-block)",
                "CRM sync (HubSpot)",
                "Background jobs",
                "AI News + Reports",
            ],
            "featured": True,
            "popular": "Most Popular",
        },
        {
            "key": "agency",
            "name": "Agency",
            "price": "$249",
            "period": "/month",
            "desc": "Run it for clients",
            "guarantee": "Unlimited verified contacts",
            "features": [
                "Unlimited leads",
                "All Pro features",
                "White-label PDF exports",
                "5 client workspaces",
                "Competitor monitoring",
                "Priority support + onboarding",
            ],
            "featured": False,
        },
    ]

    for col, plan in zip([col1, col2, col3, col4], plans_data):
        with col:
            featured_class = " featured" if plan["featured"] else ""
            popular_badge = (
                f'<div class="popular-badge">{plan["popular"]}</div>'
                if plan.get("popular") else ""
            )
            features_html = "".join(
                f'<div style="padding:0.35rem 0;font-size:0.85rem;'
                f'color:var(--text-secondary);border-bottom:1px solid var(--border-light);">✓ {f}</div>'
                for f in plan["features"]
            )
            guarantee_html = (
                f'<div style="font-size:0.75rem;color:#10b981;font-weight:600;'
                f'margin:0.75rem 0;padding:0.4rem 0.6rem;background:rgba(16,185,129,0.1);'
                f'border-radius:6px;">✅ {plan["guarantee"]}</div>'
            )
            st.markdown(
                f'<div class="pricing-card{featured_class}" style="text-align:center;">'
                f'{popular_badge}'
                f'<div class="pricing-name">{plan["name"]}</div>'
                f'<div class="pricing-price">{plan["price"]}<span>{plan["period"]}</span></div>'
                f'<div style="color:var(--text-secondary);font-size:0.82rem;margin:0.4rem 0;">{plan["desc"]}</div>'
                f'{guarantee_html}'
                f'<div style="text-align:left;">{features_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            is_current = current_plan == plan["key"]
            if is_current:
                st.button("✅ Current Plan", disabled=True, use_container_width=True, key=f"plan_{plan['key']}")
            elif plan["key"] == "free":
                if st.button("Get Started Free", use_container_width=True, key="plan_free"):
                    deactivate()
                    st.rerun()
            else:
                checkout_url = get_stripe_checkout_url(plan["key"])
                label = f"🚀 Subscribe — {plan['price']}/mo"
                if st.button(label, use_container_width=True, key=f"subscribe_{plan['key']}",
                             type="primary" if plan["featured"] else "secondary"):
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0;url={checkout_url}">',
                        unsafe_allow_html=True,
                    )
                    st.info("Redirecting to Stripe checkout...")

    st.divider()

    # ── Guarantee callout ─────────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,rgba(99,102,241,0.1),rgba(139,92,246,0.1));
        border:1px solid rgba(99,102,241,0.3);border-radius:16px;padding:1.5rem 2rem;
        margin-bottom:1.5rem;text-align:center;">
        <div style="font-size:1.3rem;font-weight:700;margin-bottom:0.5rem;">
        🛡️ What Does "Verified Contact" Mean?
        </div>
        <div style="font-size:0.92rem;color:var(--text-secondary);max-width:600px;margin:0 auto;">
        A verified contact = a real business with at least one working <strong>email OR phone number</strong>
        found during enrichment. We don't count empty rows as leads. You pay only for results.
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("📊 Full Plan Comparison")
    cmp_cols = st.columns(5)
    headers = ["Feature", "Free", "Starter", "Pro", "Agency"]
    for col, h in zip(cmp_cols, headers):
        with col:
            st.markdown(f"**{h}**")
    st.divider()

    for row in PLAN_FEATURES_LIST:
        ca, cb, cc, cd, ce = st.columns(5)
        with ca: st.markdown(row["feature"])
        with cb: st.markdown(row["free"])
        with cc: st.markdown(row.get("starter", "—"))
        with cd: st.markdown(row["pro"])
        with ce: st.markdown(row["agency"])

    st.divider()
    with st.expander("❓ Frequently Asked Questions"):
        st.markdown("**Are the contact numbers guaranteed?**")
        st.markdown(
            "Yes — we only count leads with a confirmed email or phone. "
            "You'll typically see 40–70% email hit rate and 70–80% phone hit rate from Maps."
        )
        st.markdown("**Can I switch plans anytime?**")
        st.markdown("Yes. Upgrade or downgrade instantly. Changes apply immediately.")
        st.markdown("**Is there a free trial for Pro?**")
        st.markdown("Contact us for a 7-day free trial. Or start Free and upgrade when ready.")
        st.markdown("**Can I cancel anytime?**")
        st.markdown("Yes. No lock-in. Your data stays yours forever.")
        st.markdown("**What payment methods do you accept?**")
        st.markdown("Credit/debit cards via Stripe. Secure, instant activation.")



# ── Admin Panel ──────────────────────────────────────────────────────────

def show_admin():
    st.markdown('<p class="main-header">👑 Admin Panel</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Manage users, licenses, and subscriptions</p>', unsafe_allow_html=True)

    # 1. Authentication
    if not st.session_state.get("admin_logged_in", False):
        st.info("Please enter the admin password to access this dashboard.")
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Login"):
            admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
            if pwd == admin_pass:
                st.session_state["admin_logged_in"] = True
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.error("Incorrect password.")
        return
        
    if st.button("🚪 Logout", size="small"):
        st.session_state["admin_logged_in"] = False
        st.rerun()
        
    st.divider()

    try:
        from admin_db import ADMIN_DB
    except Exception as e:
        st.error(f"Could not load Admin Database: {e}")
        return

    # 2. License Generation
    st.subheader("🔑 Generate New License")
    with st.form("gen_license"):
        col1, col2, col3 = st.columns(3)
        with col1:
            new_email = st.text_input("Customer Email", placeholder="client@company.com")
        with col2:
            new_plan = st.selectbox("Plan", ["starter", "pro", "agency"])
        with col3:
            duration = st.number_input("Duration (Days)", min_value=1, max_value=3650, value=30)
            
        submit = st.form_submit_button("Create License", type="primary")
        if submit:
            if new_email:
                key = ADMIN_DB.create_license(new_email, new_plan, duration)
                st.success(f"License created! Key: `{key}`")
            else:
                st.error("Email is required.")

    st.divider()

    # 3. Active Subscriptions Management
    st.subheader("👥 Manage Subscriptions")
    licenses = ADMIN_DB.get_all_licenses()
    
    if not licenses:
        st.info("No licenses generated yet.")
        return
        
    # Convert to dataframe for nice display
    df = pd.DataFrame(licenses)
    
    # Format dates
    import datetime
    df['created_at'] = df['created_at'].apply(lambda x: datetime.datetime.fromtimestamp(x).strftime('%Y-%m-%d'))
    df['expires_at'] = df['expires_at'].apply(lambda x: datetime.datetime.fromtimestamp(x).strftime('%Y-%m-%d') if x else "Never")
    
    # Display stats
    ca, cb, cc = st.columns(3)
    ca.metric("Total Licenses", len(df))
    cb.metric("Active", len(df[df['status'] == 'active']))
    cc.metric("Revoked", len(df[df['status'] == 'revoked']))

    for i, lic in enumerate(licenses):
        status_color = "green" if lic['status'] == "active" else "red"
        with st.expander(f"{lic['customer_email']} - {lic['plan'].upper()} ({lic['status']})"):
            st.markdown(f"**License Key:** `{lic['license_key']}`")
            st.markdown(f"**Status:** <span style='color:{status_color}'>{lic['status']}</span>", unsafe_allow_html=True)
            exp_date = datetime.datetime.fromtimestamp(lic['expires_at']).strftime('%Y-%m-%d') if lic['expires_at'] else "Never"
            st.markdown(f"**Expires:** {exp_date}")
            
            c1, c2 = st.columns(2)
            if lic['status'] == "active":
                if c1.button("🚫 Revoke Access", key=f"rev_{lic['id']}"):
                    ADMIN_DB.revoke_license(lic['license_key'])
                    st.rerun()
            else:
                if c1.button("✅ Restore Access", key=f"res_{lic['id']}"):
                    ADMIN_DB.activate_license(lic['license_key'])
                    st.rerun()


# ── Navigation ───────────────────────────────────────────────────────────




def main():
    if "nav" in st.session_state:
        nav_to = st.session_state.pop("nav", "Dashboard")
        short_map = {
            "Dashboard": "📊 Dashboard",
            "Find Leads": "🔍 Find Leads",
            "AI News": "📰 AI News",
            "Digest": "📄 Digest",
            "Database": "💾 Database",
            "Outreach": "📧 Outreach",
            "Pricing": "⚡ Pricing",
            "Admin Panel": "👑 Admin Panel",
            "Settings": "⚙️ Settings",
        }
        default_page = short_map.get(nav_to, "📊 Dashboard")
    else:
        default_page = "📊 Dashboard"

    ALL_PAGES = ["📊 Dashboard", "🔍 Find Leads", "📧 Outreach", "📰 AI News", "📄 Digest", "💾 Database", "⚡ Pricing", "👑 Admin Panel", "⚙️ Settings"]

    st.sidebar.markdown(
        '<p class="sidebar-brand">⚡ Qorvai</p>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown('<p class="sidebar-tagline">Intelligent Lead Engine</p>', unsafe_allow_html=True)
    st.sidebar.markdown(
        f'<span class="badge {"badge-pro" if is_pro() else "badge-free"}">'
        f'{"PRO" if is_pro() else "FREE"} PLAN</span>',
        unsafe_allow_html=True,
    )
    plan_name = get_plan_name()
    if is_pro():
        sub_data = get_subscription()
        plan_type = sub_data.get("plan", "pro")
        st.sidebar.caption(f"{plan_name} · {get_plan_features()['leads_per_run'] if get_plan_features()['leads_per_run'] != -1 else 'Unlimited'}/run")
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        ALL_PAGES,
        index=ALL_PAGES.index(default_page),
        label_visibility="collapsed",
    )

    if page == "📊 Dashboard":
        show_dashboard()
    elif page == "🔍 Find Leads":
        show_lead_finder()
    elif page == "📧 Outreach":
        show_outreach()
    elif page == "📰 AI News":
        show_ai_news()
    elif page == "📄 Digest":
        show_digest()
    elif page == "💾 Database":
        show_database()
    elif page == "⚡ Pricing":
        show_pricing()
    elif page == "👑 Admin Panel":
        show_admin()
    elif page == "⚙️ Settings":
        show_settings()

    st.sidebar.divider()
    dm = st.sidebar.checkbox("🌙 Dark Mode", value=st.session_state.dark_mode, key="dark_mode_toggle")
    if dm != st.session_state.dark_mode:
        st.session_state.dark_mode = dm
        st.markdown(f"<script>document.body.classList.toggle('dark-mode', {str(dm).lower()}); localStorage.setItem('qorvai_dark_mode', '{str(dm).lower()}');</script>", unsafe_allow_html=True)
        st.rerun()
    st.sidebar.caption(f"v2.0 | {datetime.now().strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    main()
