"""
backend/providers/base.py

Shared provider interface for Omnividence reverse-image-search providers.

Every provider performs a reverse-image-search of the cropped *query face* JPEG
against a public-image search engine (reached via SerpApi) and yields a list of
normalized ``ProviderResult`` dicts — one per public image hit.

HARD HONESTY / SAFETY RULES (enforced here and in every concrete provider):
  * Never fabricate results. If a provider is not configured (no SERPAPI_KEY) or
    an API/network error occurs, it returns an empty result list plus a
    human-readable ``note`` — it NEVER invents image hits.
  * No identity claims. Providers only surface PUBLIC URLs returned by the search
    engine (image_url, thumbnail_url, page_url, page_title). They never name
    people, and downstream scoring is labelled "face similarity score", never
    "match probability" or "identity confidence".

A provider must catch its own errors and degrade cleanly: ``search`` returns a
``ProviderPage`` rather than raising.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TypedDict


# --------------------------------------------------------------------------- #
# Normalized result dict EVERY provider yields (one per public image hit).
# These are the ONLY fields downstream code (search.py / cache.py) relies on.
# --------------------------------------------------------------------------- #
class ProviderResult(TypedDict):
    image_url: str                  # required, public full-res image URL (dedup key downstream)
    thumbnail_url: Optional[str]    # provider thumbnail URL, or None
    page_url: Optional[str]         # public source page URL, or None
    page_title: Optional[str]       # public source page title, or None
    provider: str                   # provider .name, e.g. "google_lens"


# --------------------------------------------------------------------------- #
# What a single page fetch returns.
# --------------------------------------------------------------------------- #
class ProviderPage(TypedDict):
    results: list[ProviderResult]   # [] if not configured or no hits — NEVER fabricated
    next_cursor: Optional[str]      # opaque continuation token to pass back next call; None => exhausted
    note: Optional[str]             # human-readable status (e.g. "provider not configured"); None on clean success


class Provider(ABC):
    """Abstract base class for a reverse-image-search provider.

    Subclasses set the ``name`` and ``engine`` class attributes and implement
    :meth:`search`. The constructor receives the shared SerpApi key (may be
    ``None``/empty), and :meth:`is_configured` gates all real work on it.
    """

    name: str       # "google_lens" | "yandex" | "bing"
    engine: str     # SerpApi engine id: "google_lens" | "yandex_images" | "bing_images"

    def __init__(self, api_key: Optional[str]):
        # From SERPAPI_KEY; may be None/empty. Stored as-is so is_configured()
        # can decide. Never logged or exposed to the frontend.
        self.api_key = api_key

    def is_configured(self) -> bool:
        """True only when a non-empty API key is present."""
        return bool(self.api_key and self.api_key.strip())

    def _not_configured_page(self) -> ProviderPage:
        """Standard honest empty page returned when no key is set.

        Centralised so every provider reports the not-configured state with the
        exact same wording: ``"<name>: provider not configured (set SERPAPI_KEY)"``.
        """
        return {
            "results": [],
            "next_cursor": None,
            "note": f"{self.name}: provider not configured (set SERPAPI_KEY)",
        }

    def _error_page(self, detail: str) -> ProviderPage:
        """Standard honest empty page on API/network error. Never raises."""
        return {
            "results": [],
            "next_cursor": None,
            "note": f"{self.name}: {detail}",
        }

    @abstractmethod
    def search(self, image_path: str, cursor: Optional[str] = None) -> ProviderPage:
        """Reverse-image-search the cropped face JPEG at ``image_path``.

        ``cursor=None`` => first page; otherwise continue from that opaque cursor
        (whatever the provider encoded — a page token or a numeric offset, as a
        JSON string).

        KEY-GATING (mandatory): if not ``self.is_configured()`` return
        :meth:`_not_configured_page` — i.e. ``{"results": [], "next_cursor": None,
        "note": "<name>: provider not configured (set SERPAPI_KEY)"}``.

        On API/network error: return :meth:`_error_page` — ``{"results": [],
        "next_cursor": None, "note": "<name>: <short error>"}``. Catch, never
        raise, never fabricate.

        On success: results parsed from the SerpApi response, ``next_cursor`` set
        from the engine's pagination (page token, or page/offset encoded as a JSON
        string) or ``None`` when no further pages exist.
        """
        ...
