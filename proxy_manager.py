"""
Proxy Pool Manager — Built-in rotating proxy system for Qorvai.

Zero-config for users: auto-fetches free proxies, tests them, rotates them.
No external VPN needed. Works out of the box.

Proxy quality tiers (best → worst):
  Tier 1: Webshare free (10 proxies, needs 1-time signup, residential-quality)
  Tier 2: ProxyScrape API  (free, no auth, datacenter)
  Tier 3: GitHub proxy lists (free, no auth, mixed quality)
  Tier 4: Direct connection  (no proxy — fallback only)

How it beats detection:
  - Each browser session gets a fresh IP from the pool
  - Dead proxies auto-removed after 2 failures
  - Pool auto-refreshes every 30 minutes
  - Combines with stealth.py fingerprint rotation for max effect
"""

import asyncio
import os
import random
import time
import threading
from collections import defaultdict
from typing import Optional

import requests

# ── Config ────────────────────────────────────────────────────────────────
POOL_SIZE          = 20          # Keep this many working proxies in pool
TEST_TIMEOUT       = 6           # Seconds to test each proxy
MAX_FAILURES       = 2           # Remove proxy after this many failures
REFRESH_INTERVAL   = 1800        # Re-fetch proxy list every 30 minutes
TEST_URL           = "http://httpbin.org/ip"   # Used to test proxies

# Free proxy sources — no signup, no API key
FREE_SOURCES = [
    # ProxyScrape — most reliable free source, updates every few minutes
    "https://api.proxyscrape.com/v3/free-proxies/api"
    "?request=displayproxies&protocol=http&timeout=8000"
    "&country=all&ssl=all&anonymity=elite,anonymous",

    # TheSpeedX GitHub list — large, updated daily
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",

    # ShiftyTR GitHub list — backup
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",

    # clarketm list
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]


class ProxyPool:
    """
    Thread-safe rotating proxy pool.
    Auto-fetches, tests, and rotates proxies.
    """

    def __init__(self):
        self._lock           = threading.Lock()
        self._pool: list[str]              = []   # working proxies
        self._failures: dict[str, int]     = defaultdict(int)
        self._last_refresh: float          = 0
        self._webshare_key: str            = os.getenv("WEBSHARE_API_KEY", "")
        self._custom_proxy: str            = os.getenv("PROXY_URL", "")
        self._stats = {
            "total_fetched": 0,
            "total_tested":  0,
            "currently_working": 0,
            "requests_proxied":  0,
            "tier": "none",
        }

    # ── Fetch ─────────────────────────────────────────────────────────────

    def _fetch_webshare(self) -> list[str]:
        """Fetch proxies from Webshare free tier (best quality, needs API key)."""
        if not self._webshare_key:
            return []
        try:
            r = requests.get(
                "https://proxy.webshare.io/api/v2/proxy/list/"
                "?mode=direct&page=1&page_size=25",
                headers={"Authorization": f"Token {self._webshare_key}"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                proxies = []
                for p in data.get("results", []):
                    proxies.append(f"http://{p['username']}:{p['password']}@{p['proxy_address']}:{p['port']}")
                print(f"[proxy] Webshare: {len(proxies)} proxies fetched")
                return proxies
        except Exception as e:
            print(f"[proxy] Webshare fetch failed: {e}")
        return []

    def _fetch_free(self) -> list[str]:
        """Fetch from free public sources."""
        proxies = set()
        for url in FREE_SOURCES:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    lines = r.text.strip().split("\n")
                    for line in lines:
                        line = line.strip()
                        if ":" in line and not line.startswith("#"):
                            # Some lists have "ip:port:user:pass" format
                            parts = line.split(":")
                            if len(parts) == 2:
                                proxies.add(f"http://{line}")
                            elif len(parts) == 4:
                                proxies.add(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
                    print(f"[proxy] {url[:60]}... → {len(lines)} raw entries")
            except Exception:
                pass
        return list(proxies)

    # ── Test ──────────────────────────────────────────────────────────────

    def _test_proxy(self, proxy_url: str) -> bool:
        """Test if a proxy works. Returns True if it can reach the internet."""
        try:
            r = requests.get(
                TEST_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=TEST_TIMEOUT,
            )
            return r.status_code == 200
        except Exception:
            return False

    def _test_batch(self, proxies: list[str], max_workers: int = 30) -> list[str]:
        """Test many proxies in parallel threads. Returns working ones."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        working = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(self._test_proxy, p): p for p in proxies}
            for future in as_completed(futures):
                proxy = futures[future]
                try:
                    if future.result():
                        working.append(proxy)
                        if len(working) >= POOL_SIZE:
                            # Cancel remaining once we have enough
                            for f in futures:
                                f.cancel()
                            break
                except Exception:
                    pass
        return working

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self, force: bool = False):
        """Fetch + test proxies, rebuild pool. Runs in background thread."""
        now = time.time()
        if not force and (now - self._last_refresh) < REFRESH_INTERVAL:
            return  # Not time yet

        print("[proxy] Refreshing proxy pool...")

        # Priority: custom env > Webshare > free lists
        if self._custom_proxy:
            with self._lock:
                self._pool = [self._custom_proxy]
                self._stats["tier"] = "custom"
                self._stats["currently_working"] = 1
            print(f"[proxy] Using custom proxy: {self._custom_proxy[:40]}")
            self._last_refresh = now
            return

        all_proxies: list[str] = []

        # Tier 1: Webshare
        ws = self._fetch_webshare()
        if ws:
            all_proxies = ws
            self._stats["tier"] = "webshare"
        else:
            # Tier 2-3: Free lists
            all_proxies = self._fetch_free()
            self._stats["tier"] = "free"

        self._stats["total_fetched"] = len(all_proxies)
        print(f"[proxy] Testing {min(len(all_proxies), 100)} proxies (parallel)...")

        # Test up to 100 randomly sampled (testing all would take forever)
        sample = random.sample(all_proxies, min(100, len(all_proxies)))
        working = self._test_batch(sample, max_workers=40)

        self._stats["total_tested"]      = len(sample)
        self._stats["currently_working"] = len(working)
        self._last_refresh = now

        with self._lock:
            self._pool     = working[:POOL_SIZE]
            self._failures = defaultdict(int)

        print(f"[proxy] Pool ready: {len(self._pool)} working proxies (tier: {self._stats['tier']})")

    def refresh_background(self):
        """Refresh pool in a background thread (non-blocking)."""
        t = threading.Thread(target=self.refresh, daemon=True)
        t.start()

    # ── Get proxy ─────────────────────────────────────────────────────────

    def get(self) -> Optional[dict]:
        """
        Get a random working proxy for Playwright.
        Returns Playwright proxy dict or None (direct connection).
        Auto-refreshes pool when empty or stale.
        """
        # Refresh if pool empty or stale
        if not self._pool or (time.time() - self._last_refresh) > REFRESH_INTERVAL:
            self.refresh()

        with self._lock:
            if not self._pool:
                return None  # Fallback: direct connection

            # Pick random proxy from pool
            proxy_url = random.choice(self._pool)
            self._stats["requests_proxied"] += 1

        return {"server": proxy_url}

    def mark_failed(self, proxy_url: str):
        """
        Mark a proxy as failed. Remove after MAX_FAILURES.
        Call this when a scraper gets blocked or times out.
        """
        with self._lock:
            self._failures[proxy_url] += 1
            if self._failures[proxy_url] >= MAX_FAILURES:
                if proxy_url in self._pool:
                    self._pool.remove(proxy_url)
                    print(f"[proxy] Removed dead proxy. Pool size: {len(self._pool)}")

                # Refresh if pool getting low
                if len(self._pool) < 5:
                    threading.Thread(target=self.refresh, kwargs={"force": True}, daemon=True).start()

    def mark_success(self, proxy_url: str):
        """Reset failure count after a successful request."""
        with self._lock:
            self._failures[proxy_url] = 0

    # ── Status ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return current pool status for display in UI."""
        with self._lock:
            age_min = int((time.time() - self._last_refresh) / 60) if self._last_refresh else -1
            return {
                "pool_size":         len(self._pool),
                "tier":              self._stats["tier"],
                "total_fetched":     self._stats["total_fetched"],
                "total_tested":      self._stats["total_tested"],
                "currently_working": self._stats["currently_working"],
                "requests_proxied":  self._stats["requests_proxied"],
                "last_refresh_min":  age_min,
                "webshare_key_set":  bool(self._webshare_key),
                "custom_proxy_set":  bool(self._custom_proxy),
                "sample_proxies":    self._pool[:3],
            }

    def force_refresh(self):
        """Force a fresh fetch + test cycle."""
        self.refresh(force=True)


# ── Module-level singleton ─────────────────────────────────────────────────
POOL = ProxyPool()

# Warm up the pool on import (background, non-blocking)
POOL.refresh_background()


# ── Convenience function (replaces stealth.get_proxy) ─────────────────────

def get_rotating_proxy() -> Optional[dict]:
    """
    Drop-in replacement for stealth.get_proxy().
    Returns a fresh rotating proxy dict for Playwright, or None.
    """
    return POOL.get()
