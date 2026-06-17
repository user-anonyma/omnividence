"""
backend/providers/yandex.py

Reverse-image-search provider: Yandex Images via SerpApi (engine="yandex_images").

Pipeline role: given the cropped *query face* JPEG, ask Yandex Images (through
SerpApi) for visually-similar PUBLIC images and return them as normalized
``ProviderResult`` dicts. Downstream the route downloads each thumbnail,
re-embeds the largest face, and scores cosine similarity — this provider only
surfaces public URLs, never identities, never fabricated hits.

HONESTY / SAFETY (mandatory):
  * Gated on SERPAPI_KEY. With no key -> [] + "provider not configured" note.
  * Any API/network/parse error -> [] + short note. Catch, never raise.
  * Never fabricates results.

SerpApi yandex_images specifics
-------------------------------
The Yandex reverse-image search needs a publicly fetchable image URL (param
``url``), not a raw local file upload. The cropped query face lives on local
disk, so to query Yandex it must be reachable over HTTP. We expose it via the
optional env var ``OMNI_PUBLIC_BASE_URL``: when set, the backend's
/api/search/{id}/query-face endpoint (which serves exactly this JPEG) is publicly
reachable and we hand SerpApi that URL.

If ``OMNI_PUBLIC_BASE_URL`` is NOT set we cannot give Yandex a fetchable image,
so we return [] with an honest note rather than fabricating — the rest of the
pipeline still runs and reports the state truthfully.

Pagination: the SerpApi yandex_images engine paginates with an integer ``page``
(0-based). We encode the NEXT page number into the opaque cursor as JSON
``{"page": N}``; ``None`` when no further pages exist.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import httpx

from .base import Provider, ProviderPage, ProviderResult

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
_REQUEST_TIMEOUT_SEC = 20.0


class YandexProvider(Provider):
    name = "yandex"
    engine = "yandex_images"

    # ------------------------------------------------------------------ #
    # cursor (de)serialization — opaque JSON string the route round-trips
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_page(cursor: Optional[str]) -> int:
        """Return the 0-based page number carried inside the opaque cursor.

        ``None``/unparseable cursor => page 0 (first page).
        """
        if not cursor:
            return 0
        try:
            data = json.loads(cursor)
        except (ValueError, TypeError):
            return 0
        if isinstance(data, dict):
            page = data.get("page")
            if isinstance(page, int) and page >= 0:
                return page
        return 0

    @staticmethod
    def _encode_page(page: Optional[int]) -> Optional[str]:
        """Wrap a next-page number into the opaque cursor JSON, or None when exhausted."""
        if page is None:
            return None
        return json.dumps({"page": page})

    # ------------------------------------------------------------------ #
    # public image URL for the query-face JPEG (required by yandex_images)
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
    # parse a single SerpApi yandex_images hit into a ProviderResult
    # ------------------------------------------------------------------ #
    def _parse_hit(self, hit: dict) -> Optional[ProviderResult]:
        if not isinstance(hit, dict):
            return None
        # SerpApi yandex_images "image_results" expose:
        #   "original_image" {"link": ...} / "original" (full-res image URL),
        #   "thumbnail" (thumb URL),
        #   "link" (source page URL), "title" / "source" (page title/site).
        image_url = (
            hit.get("original")
            or hit.get("original_image_url")
            or hit.get("image")
        )
        if not image_url:
            orig = hit.get("original_image")
            if isinstance(orig, dict):
                image_url = orig.get("link") or orig.get("url")
        if not image_url or not isinstance(image_url, str):
            # fall back to thumbnail only as a last resort (still a public URL)
            thumb = hit.get("thumbnail")
            if isinstance(thumb, str) and thumb:
                image_url = thumb
            else:
                return None  # no usable public image URL -> skip (never fabricate)

        thumbnail_url = hit.get("thumbnail")
        if not isinstance(thumbnail_url, str):
            thumbnail_url = None

        page_url = hit.get("link") or hit.get("source_url")
        if not isinstance(page_url, str):
            page_url = None

        page_title = hit.get("title") or hit.get("source")
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
    def _has_next_page(payload: dict, current_page: int) -> bool:
        """Decide whether another page exists after ``current_page``.

        Prefer SerpApi's explicit pagination metadata; fall back to "we got a
        full-looking batch" only when metadata is absent.
        """
        pag = payload.get("serpapi_pagination")
        if isinstance(pag, dict):
            # SerpApi commonly exposes a ready-made next-page request URL/flag.
            if pag.get("next") or pag.get("next_page_token"):
                return True
            other = pag.get("other_pages")
            if isinstance(other, dict):
                # keys are page numbers as strings; if any is > current+1 base
                for k in other.keys():
                    try:
                        if int(k) > current_page + 1:
                            return True
                    except (ValueError, TypeError):
                        continue
            return False
        # No metadata: assume there's more only if this page returned results.
        return False

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def search(self, image_path: str, cursor: Optional[str] = None) -> ProviderPage:
        # KEY-GATING (mandatory) ----------------------------------------
        if not self.is_configured():
            return self._not_configured_page()

        # Yandex reverse-image search needs a publicly fetchable image URL.
        public_url = self._public_image_url(image_path)
        if not public_url:
            return self._error_page(
                "yandex needs a public image URL "
                "(set OMNI_PUBLIC_BASE_URL so the query face is reachable)"
            )

        page = self._decode_page(cursor)
        params = {
            "engine": self.engine,
            "url": public_url,
            "api_key": self.api_key,
        }
        if page > 0:
            params["page"] = page

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
            payload.get("image_results")
            or payload.get("images_results")
            or []
        )
        if not isinstance(raw_hits, list):
            raw_hits = []

        results: list[ProviderResult] = []
        for hit in raw_hits:
            parsed = self._parse_hit(hit)
            if parsed is not None:
                results.append(parsed)

        # Pagination: only advance if there's evidence of a next page AND this
        # page actually returned something.
        if results and self._has_next_page(payload, page):
            next_cursor = self._encode_page(page + 1)
        else:
            next_cursor = None

        return {
            "results": results,
            "next_cursor": next_cursor,
            "note": None,  # clean success
        }
