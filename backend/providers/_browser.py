"""
backend/providers/_browser.py

Shared browser helpers for the reverse-image-search providers, built on
Scrapling's ``DynamicFetcher`` (a hardened/stealthy Playwright under the hood).

The providers need to *interact* with a page (open it, upload the cropped face,
wait for visual-search results, scrape them), so we drive everything through
``DynamicFetcher.fetch(url, page_action=...)``: the fetcher navigates to ``url``
with stealth defaults, then hands the live page to our ``page_action`` where the
upload + wait + extract happens.

Stealth here means *looking like a normal browser* so the page renders — it does
NOT mean solving or bypassing CAPTCHAs. If a CAPTCHA/anti-bot wall appears we
detect it (:func:`looks_blocked`) and stop. No proxies. No mass scraping.

Must be called from a thread with no running asyncio loop (see base.run_off_loop)
because the underlying Playwright sync API cannot run inside the event loop.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urljoin, urlparse

# Markers that signal a CAPTCHA / anti-bot WALL. Kept deliberately specific:
# bare words like "robot"/"blocked"/"captcha" appear in normal page scripts and
# would false-positive, so we match URL paths and full phrases only. Seeing these
# => stop and report "blocked"; we never try to solve or bypass them.
_BLOCK_URL_MARKERS = ("/showcaptcha", "/sorry/", "/captcha")
_BLOCK_TEXT_MARKERS = (
    "smartcaptcha",
    "are you a robot",
    "are you human",
    "verify you're not a robot",
    "verify you are not a robot",
    "unusual traffic from your",
    "our systems have detected unusual traffic",
)

# Cookie/consent buttons that sit over results and must be dismissed first.
_CONSENT_SELECTORS = (
    "button:has-text('Allow all')",
    "button:has-text('Accept all')",
    "button:has-text('Allow essential')",
    "button:has-text('I agree')",
    "button[aria-label*='Accept all' i]",
    "#L2AGLb",
)


def run_action(url: str, action: Callable, nav_timeout_ms: int = 45000) -> dict:
    """Open ``url`` with Scrapling's stealthy Chromium and run ``action(page,
    capture)`` against the live page. ``action`` populates the returned
    ``capture`` dict (e.g. ``raw`` hits, ``blocked``, ``base_url``). Any
    exception inside ``action`` is recorded as ``capture['error']`` rather than
    raised. The fetch itself may raise (browser launch failure) — callers wrap
    this in their own try/except and degrade to an honest error page.
    """
    from scrapling.fetchers import DynamicFetcher

    capture: dict = {}

    def page_action(page):
        try:
            action(page, capture)
        except Exception as exc:  # never crash the fetch; report honestly
            capture["error"] = type(exc).__name__
        return page

    DynamicFetcher.fetch(
        url,
        headless=True,
        network_idle=False,
        timeout=nav_timeout_ms,
        page_action=page_action,
        disable_resources=False,
    )
    return capture


def looks_blocked(page) -> bool:
    """Best-effort CAPTCHA / anti-bot WALL detection from the URL + page text.
    Specific by design to avoid false positives on normal result pages."""
    try:
        url = (page.url or "").lower()
        if any(m in url for m in _BLOCK_URL_MARKERS):
            return True
        body = (page.content() or "").lower()
    except Exception:
        return False
    return any(m in body for m in _BLOCK_TEXT_MARKERS)


def dismiss_consent(page) -> None:
    """Click a cookie/consent button if one is present (best-effort, no-op
    otherwise). Consent banners overlay and delay the results."""
    for sel in _CONSENT_SELECTORS:
        try:
            page.click(sel, timeout=1500)
            return
        except Exception:
            continue


def try_upload(page, image_path: str, selectors: tuple, reveal_selectors: tuple = ()) -> bool:
    """Hand ``image_path`` to a file input. Tries a present ``input[type=file]``
    first; if none, clicks each ``reveal_selectors`` (camera / "search by image"
    controls) to surface one, then retries. Returns True on success."""
    for sel in selectors:
        try:
            page.set_input_files(sel, image_path, timeout=5000)
            return True
        except Exception:
            continue
    for rev in reveal_selectors:
        try:
            page.click(rev, timeout=3000)
        except Exception:
            continue
        for sel in selectors:
            try:
                page.set_input_files(sel, image_path, timeout=5000)
                return True
            except Exception:
                continue
    return False


def absolutize(base_url: str, href) -> "str | None":
    """Resolve a possibly-relative href against the page URL; drop junk."""
    if not href or not isinstance(href, str):
        return None
    href = href.strip()
    if not href or href.startswith(("javascript:", "data:", "#")):
        return None
    try:
        absolute = urljoin(base_url, href)
    except Exception:
        return None
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return absolute
