"""
backend/providers/bing.py

Reverse-image-search provider: Bing Images via SerpApi (engine="bing_images").

Pipeline role: given the cropped *query face* JPEG, ask Bing Images (through
SerpApi) for visually-similar PUBLIC images and return them as normalized
``ProviderResult`` dicts. Downstream the route downloads each thumbnail,
re-embeds the largest face, and scores cosine similarity — this provider only
surfaces public URLs, never identities, never fabricated hits.

HONESTY / SAFETY (mandatory):
  * Gated on SERPAPI_KEY. With no key -> [] + "provider not configured" note.
  * Any API/network/parse error -> [] + short note. Catch, never raise.
  * Never fabricates results.

SerpApi bing_images specifics
-----------------------------
The Bing reverse-image search needs a publicly fetchable image URL (param
``imgurl``), not a raw local file upload. The cropped query face lives on local
disk, so to query Bing it must be reachable over HTTP. We expose it via the
optional env var ``OMNI_PUBLIC_BASE_URL``: when set, the backend's
/api/search/{id}/query-face endpoint (which serves exactly this JPEG) is publicly
reachable and we hand SerpApi that URL.

If ``OMNI_PUBLIC_BASE_URL`` is NOT set we cannot give Bing a fetchable image, so
we return [] with an honest note rather than fabricating — the rest of the
pipeline still runs and reports the state truthfully.

Pagination: the SerpApi bing_images engine paginates with an integer ``first``
result offset (1-based; first page omits it). We encode the NEXT offset into the
opaque cursor as JSON ``{"first": N}``; ``None`` when no further pages exist.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import httpx

from .base import Provider, ProviderPage, ProviderResult

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
_REQUEST_TIMEOUT_SEC = 20.0

# Bing returns results in pages; ``first`` is the 1-based offset of the first
# result on the requested page. We advance by this stride between pages.
_BING_PAGE_STRIDE = 35


class BingProvider(Provider):
    name = "bing"
    engine = "bing_images"

    # ------------------------------------------------------------------ #
    # cursor (de)serialization — opaque JSON string the route round-trips
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_first(cursor: Optional[str]) -> int:
        """Return the 1-based ``first`` offset carried inside the opaque cursor.

        ``None``/unparseable cursor => 0 (first page, ``first`` param omitted).
        """
        if not cursor:
            return 0
        try:
            data = json.loads(cursor)
        except (ValueError, TypeError):
            return 0
        if isinstance(data, dict):
            first = data.get("first")
            if isinstance(first, int) and first >= 0:
                return first
        return 0

    @staticmethod
    def _encode_first(first: Optional[int]) -> Optional[str]:
        """Wrap a next ``first`` offset into the opaque cursor JSON, or None when exhausted."""
        if first is None:
            return None
        return json.dumps({"first": first})

    # ------------------------------------------------------------------ #
    # public image URL for the query-face JPEG (required by bing_images)
    # ------------------------------------------------------------------ #
    def _public_image_url(self, image_path: str) -> Optional[str]:
        """Map the local cropped-face JPEG to a publicly fetchable URL.

        Uses OMNI_PUBLIC_BASE_URL if present. The base may already point at the
        exact query-face URL (it is per-search), or at the backend root in which
        case we append the file basename. Returns None if no public base is set.
        """
        base = os.environ.get("OMNI_PUBLIC_BASE_URL", "").strip()
        if not base:
            return None
        if base.rstrip("/").endswith("query-face"):
            return base
        return base.rstrip("/") + "/" + os.path.basename(image_path)

    # ------------------------------------------------------------------ #
    # parse a single SerpApi bing_images hit into a ProviderResult
    # ------------------------------------------------------------------ #
    def _parse_hit(self, hit: dict) -> Optional[ProviderResult]:
        if not isinstance(hit, dict):
            return None
        # SerpApi bing_images "images_results" expose:
        #   "image" / "original" (full-res image URL),
        #   "thumbnail" (thumb URL),
        #   "link" / "source" (source page URL), "title" (page title).
        image_url = (
            hit.get("original")
            or hit.get("image")
            or hit.get("image_url")
        )
        if not image_url or not isinstance(image_url, str):
            thumb = hit.get("thumbnail")
            if isinstance(thumb, str) and thumb:
                image_url = thumb
            else:
                return None  # no usable public image URL -> skip (never fabricate)

        thumbnail_url = hit.get("thumbnail")
        if not isinstance(thumbnail_url, str):
            thumbnail_url = None

        page_url = hit.get("link") or hit.get("source") or hit.get("source_url")
        if not isinstance(page_url, str):
            page_url = None

        page_title = hit.get("title")
        if not isinstance(page_title, str):
            page_title = None

        result: ProviderResult = {
            "image_url": image_url,
            "thumbnail_url": thumbnail_url,
            "page_url": page_url,
            "page_title": page_title,
            "provider": self.name,
        }
        return result

    @staticmethod
    def _has_next_page(payload: dict) -> bool:
        """Decide whether another page exists after the current one."""
        pag = payload.get("serpapi_pagination")
        if isinstance(pag, dict):
            if pag.get("next") or pag.get("next_page_token"):
                return True
            return False
        # No metadata: caller falls back to "advance if we got a full batch".
        return False

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def search(self, image_path: str, cursor: Optional[str] = None) -> ProviderPage:
        # KEY-GATING (mandatory) ----------------------------------------
        if not self.is_configured():
            return self._not_configured_page()

        # Bing reverse-image search needs a publicly fetchable image URL.
        public_url = self._public_image_url(image_path)
        if not public_url:
            return self._error_page(
                "bing needs a public image URL "
                "(set OMNI_PUBLIC_BASE_URL so the query face is reachable)"
            )

        first = self._decode_first(cursor)
        params = {
            "engine": self.engine,
            "imgurl": public_url,
            "api_key": self.api_key,
        }
        if first > 0:
            params["first"] = first

        # network + parse, all errors degrade to an honest empty page --------
        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT_SEC) as client:
                resp = client.get(SERPAPI_ENDPOINT, params=params)
        except httpx.TimeoutException:
            return self._error_page("request timed out")
        except httpx.HTTPError as exc:
            return self._error_page(f"network error ({type(exc).__name__})")
        except Exception as exc:  # never let the search path break
            return self._error_page(f"unexpected error ({type(exc).__name__})")

        if resp.status_code == 401:
            return self._error_page("unauthorized (check SERPAPI_KEY)")
        if resp.status_code == 429:
            return self._error_page("rate limited")
        if resp.status_code >= 400:
            return self._error_page(f"HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except (ValueError, json.JSONDecodeError):
            return self._error_page("invalid JSON response")

        if not isinstance(payload, dict):
            return self._error_page("unexpected response shape")

        # SerpApi reports recoverable problems via an "error" field.
        api_error = payload.get("error")
        if isinstance(api_error, str) and api_error:
            short = api_error if len(api_error) <= 120 else api_error[:117] + "..."
            return self._error_page(short)

        raw_hits = (
            payload.get("images_results")
            or payload.get("image_results")
            or []
        )
        if not isinstance(raw_hits, list):
            raw_hits = []

        results: list[ProviderResult] = []
        for hit in raw_hits:
            parsed = self._parse_hit(hit)
            if parsed is not None:
                results.append(parsed)

        # Pagination: advance ``first`` when SerpApi signals a next page, or when
        # we received a full-looking batch (no explicit metadata but more likely).
        if results and (self._has_next_page(payload) or len(results) >= _BING_PAGE_STRIDE):
            next_first = (first if first > 0 else 1) + _BING_PAGE_STRIDE
            next_cursor = self._encode_first(next_first)
        else:
            next_cursor = None

        return {
            "results": results,
            "next_cursor": next_cursor,
            "note": None,  # clean success
        }
