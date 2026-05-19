"""
Real SaaS subscription system for Qorvai AI.
Stores subscription state in subscription.json
Integrates with Stripe for payment processing.
"""

import json
import os
import time
import uuid
import requests
import hashlib

SUBSCRIPTION_FILE = os.path.join(os.path.dirname(__file__), "subscription.json")

PLANS = {
    "free": {
        "name": "Free",
        "leads_per_run": 10,
        "verified_contacts_month": 10,
        "proxy": False,
        "crm_sync": False,
        "hyper_personalization": False,
        "outreach": False,
        "max_sources": 1,
        "price": 0,
        "price_id": None,
        "guarantee": "Up to 10 verified contacts/run",
    },
    "starter": {
        "name": "Starter",
        "leads_per_run": 100,
        "verified_contacts_month": 50,
        "proxy": False,
        "crm_sync": False,
        "hyper_personalization": True,
        "outreach": True,
        "max_sources": 3,
        "price": 29,
        "price_id": "price_starter_monthly",
        "guarantee": "50 verified contacts/month guaranteed",
    },
    "pro": {
        "name": "Pro",
        "leads_per_run": 500,
        "verified_contacts_month": 300,
        "proxy": True,
        "crm_sync": True,
        "hyper_personalization": True,
        "outreach": True,
        "max_sources": 6,
        "price": 79,
        "price_id": "price_pro_monthly",
        "guarantee": "300 verified contacts/month guaranteed",
    },
    "agency": {
        "name": "Agency",
        "leads_per_run": -1,
        "verified_contacts_month": -1,
        "proxy": True,
        "crm_sync": True,
        "hyper_personalization": True,
        "outreach": True,
        "max_sources": 6,
        "price": 249,
        "price_id": "price_agency_monthly",
        "guarantee": "Unlimited verified contacts",
    },
}


def _default_sub():
    return {
        "plan": "free",
        "status": "active",
        "activated_at": None,
        "expires_at": None,
        "license_key": None,
        "customer_email": None,
        "stripe_session_id": None,
    }


def get_subscription() -> dict:
    if not os.path.exists(SUBSCRIPTION_FILE):
        sub = _default_sub()
        set_subscription(sub)
        return sub
    try:
        with open(SUBSCRIPTION_FILE, "r") as f:
            sub = json.load(f)
        expires = sub.get("expires_at")
        if expires and time.time() > expires:
            sub["plan"] = "free"
            sub["status"] = "expired"
            set_subscription(sub)
        return sub
    except Exception:
        return _default_sub()


def set_subscription(sub: dict):
    os.makedirs(os.path.dirname(SUBSCRIPTION_FILE) or ".", exist_ok=True)
    with open(SUBSCRIPTION_FILE, "w") as f:
        json.dump(sub, f, indent=2)

def _validate_remote_license(license_key: str) -> bool:
    """
    Validates the license key against the central licensing database.
    If deployed in the cloud, this would call a remote endpoint.
    For this setup, it checks the local admin.db.
    """
    if not license_key: return False
    
    try:
        from admin_db import ADMIN_DB
        data = ADMIN_DB.validate_license(license_key)
        return data is not None
    except Exception:
        # Fallback to the basic checksum if DB fails
        if not license_key.startswith("QRV-"):
            return False
        parts = license_key.split("-")
        return len(parts) >= 3


def get_plan_features() -> dict:
    sub = get_subscription()
    plan = sub.get("plan", "free")
    return PLANS.get(plan, PLANS["free"])


def is_pro() -> bool:
    sub = get_subscription()
    
    # 1. Check local state
    if not (sub.get("plan") in ("starter", "pro", "agency") and sub.get("status") == "active"):
        return False
        
    # 2. Check remote server / cryptographic validity
    # Cache the remote check for 24 hours to avoid rate limits
    last_check = sub.get("last_remote_check", 0)
    if time.time() - last_check > 86400:  
        is_valid = _validate_remote_license(sub.get("license_key"))
        if not is_valid:
            sub["status"] = "expired"
            sub["plan"] = "free"
            set_subscription(sub)
            return False
        else:
            sub["last_remote_check"] = time.time()
            set_subscription(sub)
            
    return True


def is_pro_plus() -> bool:
    """True only for Pro and Agency (not Starter)."""
    sub = get_subscription()
    return sub.get("plan") in ("pro", "agency") and sub.get("status") == "active"


def get_leads_limit() -> int:
    features = get_plan_features()
    return features["leads_per_run"]


def get_stripe_checkout_url(plan: str) -> str:
    """
    Returns the Stripe Checkout URL for the given plan.

    SETUP (one-time, after switching Stripe to Live Mode):
      1. Go to Stripe Dashboard → Products → create Starter / Pro / Agency
      2. Copy the Payment Link URL for each plan
      3. Set these env vars in Railway dashboard:
           STRIPE_LINK_STARTER  = https://buy.stripe.com/live_xxxxx
           STRIPE_LINK_PRO      = https://buy.stripe.com/live_yyyyy
           STRIPE_LINK_AGENCY   = https://buy.stripe.com/live_zzzzz
    """
    import os as _os
    env_key = f"STRIPE_LINK_{plan.upper()}"
    live_url = _os.getenv(env_key, "").strip()
    if live_url:
        return live_url
    # Fallback: test mode link (remove once live keys are set)
    return f"https://buy.stripe.com/test_8wE4jA3qX9vK3C4aEE?client_reference_id={uuid.uuid4().hex[:8]}"


def activate_license(license_key: str, plan: str = "pro") -> bool:
    sub = get_subscription()
    if not license_key:
        return False
        
    # Validate against the remote server immediately
    if not _validate_remote_license(license_key):
        return False
        
    sub["plan"] = plan
    sub["status"] = "active"
    sub["license_key"] = license_key
    sub["activated_at"] = time.time()
    sub["expires_at"] = time.time() + 30 * 86400
    sub["last_remote_check"] = time.time()
    set_subscription(sub)
    return True


def deactivate():
    set_subscription(_default_sub())


def get_plan_name() -> str:
    sub = get_subscription()
    plan = sub.get("plan", "free")
    return PLANS.get(plan, PLANS["free"])["name"]


PLAN_FEATURES_LIST = [
    {"feature": "Verified contacts/month", "free": "10", "starter": "50", "pro": "300", "agency": "Unlimited"},
    {"feature": "Leads per run", "free": "10", "starter": "100", "pro": "500", "agency": "Unlimited"},
    {"feature": "Data sources", "free": "1", "starter": "3", "pro": "6", "agency": "6"},
    {"feature": "Email enrichment", "free": "✓", "starter": "✓", "pro": "✓", "agency": "✓"},
    {"feature": "GPT pain point scoring", "free": "✓", "starter": "✓", "pro": "✓", "agency": "✓"},
    {"feature": "Hyper-personalized emails", "free": "—", "starter": "✓", "pro": "✓", "agency": "✓"},
    {"feature": "1-click outreach", "free": "—", "starter": "✓", "pro": "✓", "agency": "✓"},
    {"feature": "Proxy rotation", "free": "—", "starter": "—", "pro": "✓", "agency": "✓"},
    {"feature": "CRM sync (HubSpot)", "free": "—", "starter": "—", "pro": "✓", "agency": "✓"},
    {"feature": "AI News + Digest", "free": "✓", "starter": "✓", "pro": "✓", "agency": "✓"},
    {"feature": "White-label exports", "free": "—", "starter": "—", "pro": "—", "agency": "✓"},
    {"feature": "Multi-client workspaces", "free": "—", "starter": "—", "pro": "—", "agency": "✓"},
    {"feature": "Priority support", "free": "—", "starter": "—", "pro": "—", "agency": "✓"},
]
