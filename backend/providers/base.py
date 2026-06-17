"""
backend/providers/base.py

Shared provider interface for Omnividence reverse-image-search providers.

Every provider performs a reverse-image-search of the cropped *query face* JPEG
against a public-image search engine by driving the engine's REAL public web page
with a headless Chromium (Playwright) — uploading the local cropped face, waiting
for the visual-search results, and scraping the public result links. It yields a
list of normalized ``ProviderResult`` dicts — one per public image hit.

HARD HONESTY / SAFETY RULES (enforced here and in every concrete provider):
  * Never fabricate results. If the browser is unavailable, the page is blocked
    by a CAPTCHA / anti-bot wall, or any error occurs, the provider returns an
    empty result list plus a human-readable ``note`` — it NEVER invents hits.
  * Do NOT bypass CAPTCHAs, do NOT use proxies, do NOT mass-scrape. Each provider
    is capped at ``RESULT_LIMIT`` (20) results for a controlled school demo. If a
    CAPTCHA/anti-bot page is detected, the provider stops and reports it honestly.
  * No identity claims. Providers only surface PUBLIC URLs the engine returned
    (image_url, thumbnail_url, page_url, page_title). They never name people, and
    downstream scoring is labelled "visual face similarity", never "match
    probability" or "identity confidence".

Threading: the route handler is ``async``; Playwright's *sync* API cannot run
inside a running asyncio event loop. So :meth:`Provider.search` runs the actual
browser work in a dedicated worker thread (:func:`run_off_loop`), which has no
running loop — robust no matter how the route calls us.

A provider must catch its own errors and degrade cleanly: ``search`` returns a
``ProviderPage`` rather than raising.
"""

from __future__ import annotations

import concurrent.futures
from abc import ABC, abstractmethod
from typing import Optional, TypedDict

# Per-provider hard cap for the school demo (no mass scraping).
RESULT_LIMIT: int = 20


# --------------------------------------------------------------------------- #
# Normalized result dict EVERY provider yields (one per public image hit).
# These are the ONLY fields downstream code (search.py / cache.py) relies on.
# --------------------------------------------------------------------------- #
class ProviderResult(TypedDict):
    image_url: str                  # required, public image URL (dedup key downstream)
    thumbnail_url: Optional[str]    # provider thumbnail URL, or None
    page_url: Optional[str]         # public source page URL, or None
    page_title: Optional[str]       # public source page title, or None
    provider: str                   # provider .name, e.g. "yandex"


# --------------------------------------------------------------------------- #
# What a single page fetch returns.
# --------------------------------------------------------------------------- #
class ProviderPage(TypedDict):
    results: list[ProviderResult]   # [] if blocked / unavailable / no hits — NEVER fabricated
    next_cursor: Optional[str]      # opaque continuation token; None => exhausted (one page per demo)
    note: Optional[str]             # human-readable status (e.g. "blocked by captcha"); None on clean success


def browser_available() -> bool:
    """True when Scrapling's browser fetcher is importable. The Chromium browser
    binary is checked lazily at launch — a missing browser degrades to an honest
    error note, never a crash."""
    try:
        from scrapling.fetchers import DynamicFetcher  # noqa: F401
    except Exception:
        return False
    return True


def run_off_loop(fn, *args, timeout: float = 90.0):
    """Run ``fn(*args)`` in a fresh worker thread and return its result.

    Playwright's sync API refuses to run inside a thread that has a running
    asyncio loop (the FastAPI handler). A dedicated thread has no running loop,
    so sync Playwright works there. The event-loop thread blocks on the result,
    which is fine for a single-user school demo.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn, *args).result(timeout=timeout)


class Provider(ABC):
    """Abstract base class for a reverse-image-search provider.

    Subclasses set the ``name`` class attribute and implement :meth:`_scrape`,
    which runs the Playwright browser work (it is invoked off the event loop by
    :meth:`search`). They never raise out of ``search``.
    """

    name: str          # "yandex" | "bing" | "google_lens"
    result_limit: int = RESULT_LIMIT

    def __init__(self, api_key: Optional[str] = None):
        # Browser-automation providers take no API key. The optional arg is kept
        # only so the registry/route call sites stay stable; it is ignored.
        self._unused_api_key = api_key

    def is_configured(self) -> bool:
        """True when the provider can run — i.e. Playwright is importable."""
        return browser_available()

    def _unavailable_page(self) -> ProviderPage:
        """Honest empty page when the browser stack is unavailable."""
        return {
            "results": [],
            "next_cursor": None,
            "note": f"{self.name}: browser automation unavailable "
            f"(install deps + run 'scrapling install' to fetch the browser)",
        }

    def _blocked_page(self) -> ProviderPage:
        """Honest empty page when a CAPTCHA / anti-bot wall is hit. We do NOT
        attempt to bypass it."""
        return {
            "results": [],
            "next_cursor": None,
            "note": f"{self.name}: blocked (captcha/anti-bot) — no results",
        }

    def _error_page(self, detail: str) -> ProviderPage:
        """Honest empty page on any browser/parse error. Never raises."""
        return {"results": [], "next_cursor": None, "note": f"{self.name}: {detail}"}

    def _ok_page(self, results: list[ProviderResult]) -> ProviderPage:
        """Clean success page, capped at ``result_limit`` and de-duped by image_url."""
        seen: set[str] = set()
        capped: list[ProviderResult] = []
        for r in results:
            url = r.get("image_url")
            if not url or url in seen:
                continue
            seen.add(url)
            r.setdefault("provider", self.name)
            capped.append(r)
            if len(capped) >= self.result_limit:
                break
        note = None if capped else f"{self.name}: no results found"
        # One page per provider for the demo (no pagination / mass scraping).
        return {"results": capped, "next_cursor": None, "note": note}

    def search(self, image_path: str, cursor: Optional[str] = None) -> ProviderPage:
        """Reverse-image-search the cropped face JPEG at ``image_path``.

        Demo policy: a single page of up to ``result_limit`` (20) results per
        provider; ``next_cursor`` is always ``None`` (no pagination / mass
        scraping). Runs the browser off the event loop and never raises.
        """
        if not self.is_configured():
            return self._unavailable_page()
        try:
            return run_off_loop(self._scrape, image_path)
        except concurrent.futures.TimeoutError:
            return self._error_page("timed out waiting for results")
        except Exception as exc:  # never let the search path break
            return self._error_page(f"error ({type(exc).__name__})")

    @abstractmethod
    def _scrape(self, image_path: str) -> ProviderPage:
        """Drive the provider's public reverse-image page with Playwright:
        open it, upload the cropped face, wait for visual-search results, scrape
        up to ``result_limit`` public hits, and return them via :meth:`_ok_page`.
        Detect CAPTCHA/anti-bot walls and return :meth:`_blocked_page`. Catch all
        errors and return :meth:`_error_page`. NEVER fabricate results."""
        ...
