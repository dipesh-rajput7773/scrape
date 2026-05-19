"""
Niche → Source Router

For every niche, defines:
  - Which scraping sources to use (in priority order)
  - Search keywords per source
  - Where businesses in this niche actually list themselves

This is the BRAIN of the multi-source engine.
Add new niches here — scrapers pick it up automatically.
"""

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE IDs used across the system
# ─────────────────────────────────────────────────────────────────────────────
# maps          → Google Maps          (local businesses, universal)
# yelp          → Yelp                 (local services, restaurants)
# clutch        → Clutch.co            (IT agencies, marketing firms)
# healthgrades  → Healthgrades         (doctors, dentists, clinics)
# tripadvisor   → TripAdvisor          (restaurants, hotels, tourism)
# facebook      → Facebook Pages       (universal — every business has one)
# dork          → DuckDuckGo dorking   (email harvesting, any niche)
# ─────────────────────────────────────────────────────────────────────────────

NICHE_CONFIG = {

    # ── IT / Tech / Agency ────────────────────────────────────────────────

    "Digital Marketing Agency": {
        "sources": ["clutch", "maps", "facebook", "dork"],
        "keywords": {
            "maps":    ["digital marketing agency", "social media agency", "marketing company"],
            "clutch":  ["digital marketing"],
            "facebook":["digital marketing agency"],
            "dork":    ["digital marketing agency"],
        },
        "clutch_category": "digital-marketing",
        "description": "Agencies selling SEO, ads, social media to businesses",
    },

    "Web Design / Dev Agency": {
        "sources": ["clutch", "maps", "facebook", "dork"],
        "keywords": {
            "maps":    ["web design agency", "web development company", "software company"],
            "clutch":  ["web design", "web development"],
            "facebook":["web design agency"],
            "dork":    ["web design agency"],
        },
        "clutch_category": "web-designers",
        "description": "Agencies selling websites, apps, software",
    },

    "AI / Automation Agency": {
        "sources": ["clutch", "maps", "facebook", "dork"],
        "keywords": {
            "maps":    ["AI agency", "automation company", "chatbot development"],
            "clutch":  ["artificial intelligence", "automation"],
            "facebook":["AI automation agency"],
            "dork":    ["AI automation agency"],
        },
        "clutch_category": "artificial-intelligence",
        "description": "Agencies selling AI, n8n, chatbots, automation",
    },

    "SEO Agency": {
        "sources": ["clutch", "maps", "dork"],
        "keywords": {
            "maps":    ["SEO agency", "SEO company", "search engine optimization"],
            "clutch":  ["seo"],
            "dork":    ["SEO agency"],
        },
        "clutch_category": "seo-firms",
        "description": "Agencies selling SEO services",
    },

    # ── Healthcare ────────────────────────────────────────────────────────

    "Dentist": {
        "sources": ["maps", "healthgrades", "yelp", "facebook", "dork"],
        "keywords": {
            "maps":        ["dentist", "dental clinic", "dental office"],
            "healthgrades":["dentist"],
            "yelp":        ["dentist"],
            "facebook":    ["dental clinic"],
            "dork":        ["dentist"],
        },
        "healthgrades_specialty": "dentists",
        "description": "Dental clinics and individual dentists",
    },

    "Doctor / Clinic": {
        "sources": ["maps", "healthgrades", "yelp", "facebook"],
        "keywords": {
            "maps":        ["medical clinic", "doctor", "physician", "general practitioner"],
            "healthgrades":["doctor"],
            "yelp":        ["medical clinic"],
            "facebook":    ["medical clinic"],
        },
        "healthgrades_specialty": "doctors",
        "description": "General practitioners, clinics, medical centers",
    },

    "Hospital": {
        "sources": ["maps", "healthgrades", "facebook", "dork"],
        "keywords": {
            "maps":        ["hospital", "medical center", "healthcare"],
            "healthgrades":["hospital"],
            "facebook":    ["hospital"],
            "dork":        ["hospital contact email"],
        },
        "healthgrades_specialty": "hospitals",
        "description": "Hospitals and large medical centers",
    },

    "Physiotherapist": {
        "sources": ["maps", "healthgrades", "yelp", "dork"],
        "keywords": {
            "maps":        ["physiotherapist", "physical therapy", "physio clinic"],
            "healthgrades":["physical therapist"],
            "yelp":        ["physical therapy"],
            "dork":        ["physiotherapy clinic"],
        },
        "healthgrades_specialty": "physical-therapists",
        "description": "Physio clinics, rehabilitation centers",
    },

    # ── Food & Hospitality ────────────────────────────────────────────────

    "Restaurant": {
        "sources": ["maps", "tripadvisor", "yelp", "facebook"],
        "keywords": {
            "maps":        ["restaurant", "cafe", "bistro", "eatery"],
            "tripadvisor": ["restaurant"],
            "yelp":        ["restaurant"],
            "facebook":    ["restaurant"],
        },
        "description": "Restaurants, cafes, bistros",
    },

    "Hotel": {
        "sources": ["maps", "tripadvisor", "facebook", "dork"],
        "keywords": {
            "maps":        ["hotel", "resort", "boutique hotel"],
            "tripadvisor": ["hotel"],
            "facebook":    ["hotel"],
            "dork":        ["hotel reservations email"],
        },
        "description": "Hotels, resorts, boutique stays",
    },

    # ── Fitness & Wellness ────────────────────────────────────────────────

    "Gym / Fitness": {
        "sources": ["maps", "yelp", "facebook", "dork"],
        "keywords": {
            "maps":    ["gym", "fitness center", "crossfit", "yoga studio"],
            "yelp":    ["gym"],
            "facebook":["gym fitness center"],
            "dork":    ["gym fitness studio"],
        },
        "description": "Gyms, fitness centers, yoga studios, crossfit boxes",
    },

    "Salon / Spa": {
        "sources": ["maps", "yelp", "facebook", "dork"],
        "keywords": {
            "maps":    ["hair salon", "beauty salon", "spa", "nail salon"],
            "yelp":    ["hair salon"],
            "facebook":["hair salon beauty"],
            "dork":    ["beauty salon"],
        },
        "description": "Hair salons, beauty salons, day spas",
    },

    # ── Real Estate ───────────────────────────────────────────────────────

    "Real Estate Agent": {
        "sources": ["maps", "facebook", "dork"],
        "keywords": {
            "maps":    ["real estate agent", "realtor", "property agent"],
            "facebook":["real estate agent"],
            "dork":    ["real estate agent contact email"],
        },
        "description": "Independent real estate agents and small agencies",
    },

    "Real Estate Agency": {
        "sources": ["maps", "clutch", "facebook", "dork"],
        "keywords": {
            "maps":    ["real estate agency", "property management", "estate agent"],
            "clutch":  ["real estate"],
            "facebook":["real estate agency"],
            "dork":    ["real estate agency contact"],
        },
        "clutch_category": "real-estate",
        "description": "Real estate agencies and property management firms",
    },

    # ── Legal ─────────────────────────────────────────────────────────────

    "Law Firm": {
        "sources": ["maps", "facebook", "dork"],
        "keywords": {
            "maps":    ["law firm", "lawyer", "attorney", "legal services"],
            "facebook":["law firm"],
            "dork":    ["law firm contact email"],
        },
        "description": "Law firms, legal consultancies, solo attorneys",
    },

    # ── Finance ───────────────────────────────────────────────────────────

    "Accounting / CA Firm": {
        "sources": ["maps", "clutch", "facebook", "dork"],
        "keywords": {
            "maps":    ["accounting firm", "chartered accountant", "bookkeeping"],
            "clutch":  ["accounting"],
            "facebook":["accounting firm"],
            "dork":    ["accounting firm contact email"],
        },
        "clutch_category": "accounting",
        "description": "Accounting firms, CA firms, bookkeeping services",
    },

    # ── Home Services ─────────────────────────────────────────────────────

    "Contractor / Builder": {
        "sources": ["maps", "yelp", "facebook", "dork"],
        "keywords": {
            "maps":    ["contractor", "construction company", "builder", "renovation"],
            "yelp":    ["contractor"],
            "facebook":["construction contractor"],
            "dork":    ["construction contractor contact"],
        },
        "description": "General contractors, builders, renovation companies",
    },

    "Interior Designer": {
        "sources": ["maps", "clutch", "facebook", "dork"],
        "keywords": {
            "maps":    ["interior designer", "interior design studio"],
            "clutch":  ["interior design"],
            "facebook":["interior design"],
            "dork":    ["interior design studio email"],
        },
        "clutch_category": "interior-design",
        "description": "Interior design studios and individual designers",
    },

    # ── Education ─────────────────────────────────────────────────────────

    "Tutoring / Education": {
        "sources": ["maps", "facebook", "yelp", "dork"],
        "keywords": {
            "maps":    ["tutoring center", "coaching institute", "learning center"],
            "yelp":    ["tutoring"],
            "facebook":["tutoring center"],
            "dork":    ["tutoring center contact email"],
        },
        "description": "Tutoring centers, coaching institutes, online tutors",
    },

    # ── Auto ──────────────────────────────────────────────────────────────

    "Auto Repair / Garage": {
        "sources": ["maps", "yelp", "facebook", "dork"],
        "keywords": {
            "maps":    ["auto repair", "car service", "mechanic", "garage"],
            "yelp":    ["auto repair"],
            "facebook":["auto repair garage"],
            "dork":    ["auto repair shop contact"],
        },
        "description": "Auto repair shops, car service centers, garages",
    },

    # ── Recruitment ───────────────────────────────────────────────────────

    "Recruitment Agency": {
        "sources": ["clutch", "maps", "facebook", "dork"],
        "keywords": {
            "maps":    ["recruitment agency", "staffing agency", "HR consultancy"],
            "clutch":  ["hr outsourcing", "staffing"],
            "facebook":["recruitment agency"],
            "dork":    ["recruitment agency contact email"],
        },
        "clutch_category": "hr-outsourcing",
        "description": "Recruitment, staffing, HR consulting firms",
    },
}

# ── Source display names ──────────────────────────────────────────────────
SOURCE_LABELS = {
    "maps":         "🗺️ Google Maps",
    "yelp":         "⭐ Yelp",
    "clutch":       "🏆 Clutch.co",
    "healthgrades": "🏥 Healthgrades",
    "tripadvisor":  "✈️ TripAdvisor",
    "facebook":     "📘 Facebook Pages",
    "dork":         "🔍 Web Dorking",
}

# ── Helper functions ──────────────────────────────────────────────────────

def get_sources(niche: str) -> list[str]:
    """Return ordered list of sources for a given niche."""
    config = NICHE_CONFIG.get(niche, {})
    return config.get("sources", ["maps", "dork"])


def get_keywords(niche: str, source: str) -> list[str]:
    """Return search keywords for a niche+source combo."""
    config = NICHE_CONFIG.get(niche, {})
    keywords = config.get("keywords", {}).get(source, [niche])
    return keywords if keywords else [niche]


def get_clutch_category(niche: str) -> str:
    """Return Clutch.co category slug for niche."""
    return NICHE_CONFIG.get(niche, {}).get("clutch_category", "")


def get_healthgrades_specialty(niche: str) -> str:
    """Return Healthgrades specialty slug for niche."""
    return NICHE_CONFIG.get(niche, {}).get("healthgrades_specialty", "")


def all_niches() -> list[str]:
    """Return all supported niches."""
    return list(NICHE_CONFIG.keys())


def describe(niche: str) -> str:
    """Return human-readable description of the niche."""
    return NICHE_CONFIG.get(niche, {}).get("description", niche)
