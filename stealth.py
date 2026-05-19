"""
Anti-detection & stealth utilities for all Qorvai scrapers.
Provides human-like browser fingerprints, stealth patches, and proxy rotation.

Usage:
    from stealth import StealthBrowser
    async with StealthBrowser(headless=True) as ctx:
        page = await ctx.new_page()
"""

import asyncio
import os
import random
import re

# ── Realistic User-Agent pool (rotated per session) ─────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

# ── Realistic viewport pool ─────────────────────────────────────────────
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]

# ── Timezone & locale pool ──────────────────────────────────────────────
LOCALES = ["en-US", "en-GB", "en-AU", "en-CA", "en-IN"]
TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Los_Angeles",
    "Europe/London", "Europe/Paris", "Asia/Dubai", "Asia/Kolkata",
    "Australia/Sydney", "Asia/Tokyo", "Asia/Singapore",
]

# ── macOS color depths & screen specs for fingerprint diversity ─────────
COLOR_DEPTHS = [24, 30, 48]
DEVICE_MEMORY = [4, 8, 16, 32]


def random_ua() -> str:
    return random.choice(USER_AGENTS)


def random_viewport() -> dict:
    return random.choice(VIEWPORTS)


def random_locale() -> str:
    return random.choice(LOCALES)


def random_timezone() -> str:
    return random.choice(TIMEZONES)


def get_proxy() -> dict | None:
    """
    Returns a rotating proxy from the pool.
    Falls back to direct connection if pool is empty.
    All scrapers call this — zero config for users.
    """
    try:
        from proxy_manager import get_rotating_proxy
        return get_rotating_proxy()
    except Exception:
        # Fallback: single static proxy from env (old behaviour)
        proxy_url = os.getenv("PROXY_URL", "").strip()
        if proxy_url:
            return {"server": proxy_url}
        return None


async def patch_page(page):
    """Apply stealth patches to hide Playwright/bot fingerprints."""
    await page.add_init_script("""
        // Override navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        
        // Override chrome.runtime
        window.chrome = {
            runtime: { 
                onConnect: { addListener: () => {} },
                onMessage: { addListener: () => {} },
                sendMessage: () => {},
                getPlatformInfo: () => 'win32',
                getManifest: () => ({ version: '126.0.0.0' })
            },
            loadTimes: () => ({}),
            csi: () => ({}),
            app: { isInstalled: false },
        };
        
        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ]
        });
        
        // Override languages
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        
        // Override hardwareConcurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        
        // Override deviceMemory
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        // Remove webdriver from prototype
        delete navigator.__proto__.webdriver;
        
        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
    """)


async def human_scroll(page, distance: int = None, steps: int = None):
    """Scroll with human-like random intervals."""
    if distance is None:
        distance = random.randint(300, 1200)
    if steps is None:
        steps = random.randint(3, 7)
    step_size = distance // steps
    for _ in range(steps):
        await page.mouse.wheel(0, step_size + random.randint(-20, 20))
        await asyncio.sleep(random.uniform(0.15, 0.45))


async def human_type(page, selector: str, text: str):
    """Type text with human-like random delays between keystrokes."""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.1, 0.3))
    for char in text:
        await page.keyboard.type(char, delay=random.randint(30, 120))


async def random_delay(min_s: float = 0.5, max_s: float = 2.5):
    """Wait a random amount of time to look human."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def create_stealth_context(browser, viewport: dict = None, locale: str = None,
                                 timezone_id: str = None, ua: str = None):
    """Create a browser context with randomized fingerprints."""
    if viewport is None:
        viewport = random_viewport()
    if locale is None:
        locale = random_locale()
    if timezone_id is None:
        timezone_id = random_timezone()
    if ua is None:
        ua = random_ua()

    ctx = await browser.new_context(
        user_agent=ua,
        viewport=viewport,
        locale=locale,
        timezone_id=timezone_id,
        color_scheme=random.choice(["light", "dark"]),
        device_scale_factor=random.choice([1, 2]),
        is_mobile="iPhone" in ua or "Android" in ua,
        has_touch="iPhone" in ua or "Android" in ua,
    )

    # Set extra HTTP headers to look more legit
    await ctx.set_extra_http_headers({
        "Accept-Language": locale.replace("_", "-"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })

    return ctx
