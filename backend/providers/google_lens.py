"""
backend/providers/google_lens.py

MVP reverse-image-search provider: Google Lens via SerpApi (engine="google_lens").

Pipeline role: given the cropped *query face* JPEG, ask Google Lens (through
SerpApi) for visually-similar PUBLIC images and return them as normalized
``ProviderResult`` dicts. Downstream the route downloads each thumbnail,
re-embeds the largest face, and scores cosine similarity — this provider only
surfaces public URLs, never identities, never fabricated hits.

HONESTY / SAFETY (mandatory):
  * Gated on SERPAPI_KEY. With no key -> [] + "provider not configured" note.
  * Any API/network/parse error -> [] + short note. Catch, never raise.
  * Never fabricates results.

SerpApi google_lens specifics
-----------------------------
The Google Lens engine searches a PUBLIC image URL (param ``url``), not a raw file
upload. The cropped query face lives on local disk, so to query Google Lens it
must be reachable over HTTP. We expose it via the optional env var
``OMNI_PUBLIC_BASE_URL``: when set, the backend's /api/search/{id}/query-face
endpoint (which serves exactly this JPEG) is publicly reachable at
``<OMNI_PUBLIC_BASE_URL>`` and we hand SerpApi that URL.

If ``OMNI_PUBLIC_BASE_URL`` is NOT set we cannot give Google Lens a fetchable
image, so we return [] with an honest note rather than fabricating — the rest of
the pipeline still runs and reports the state truthfully.

Pagination: SerpApi google_lens returns a page token at
``serpapi_pagination.next_page_token`` (sometimes ``next_page_token`` at the
root). We encode it into the opaque cursor as JSON ``{"page_token": "<tok>"}``;
``None`` when no further pages exist.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import httpx

from .base import Provider, ProviderPage, ProviderResult

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
_REQUEST_TIMEOUT_SEC = 20.0


class GoogleLensProvider(Provider):
    name = "google_lens"
    engine = "google_lens"

    # ------------------------------------------------------------------ #
    # cursor (de)serialization — opaque JSON string the route round-trips
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_cursor(cursor: Optional[str]) -> Optional[str]:
        """Return the page_token carried inside the opaque cursor, or None."""
        if not cursor:
            return None
        try:
            data = json.loads(cursor)
        except (ValueError, TypeError):
            # Tolerate a bare token string for robustness.
            return cursor or None
        if isinstance(data, dict):
            tok = data.get("page_token")
            return tok if isinstance(tok, str) and tok else None
        return None

    @staticmethod
    def _encode_cursor(page_token: Optional[str]) -> Optional[str]:
        """Wrap a page token into the opaque cursor JSON, or None when exhausted."""
        if not page_token:
            return None
        return json.dumps({"page_token": page_token})

    # ------------------------------------------------------------------ #
    # public image URL for the query-face JPEG (required by google_lens)
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
        # If the operator points the base directly at a query-face URL, use it
        # verbatim; otherwise join the basename of the served JPEG.
        if base.rstrip("/").endswith("query-face"):
            return base
        return base.rstrip("/") + "/" + os.path.basename(image_path)

    # ------------------------------------------------------------------ #
    # parse a single SerpApi google_lens hit into a ProviderResult
    # ------------------------------------------------------------------ #
    def _parse_hit(self, hit: dict) -> Optional[ProviderResult]:
        if not isinstance(hit, dict):
            return None
        # SerpApi google_lens visual matches expose:
        #   "image" / "thumbnail" (image URLs),
        #   "link" (source page URL), "title" / "source" (page title/site).
        image_url = (
            hit.get("image")
            or hit.get("original")
            or hit.get("image_url")
            or hit.get("thumbnail")
        )
        if not image_url or not isinstance(image_url, str):
            return None  # no usable public image URL -> skip (never fabricate one)

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
    def _extract_next_token(payload: dict) -> Optional[str]:
        """Pull the next-page token from a SerpApi google_lens response."""
        pag = payload.get("serpapi_pagination")
        if isinstance(pag, dict):
            tok = pag.get("next_page_token")
            if isinstance(tok, str) and tok:
                return tok
        tok = payload.get("next_page_token")
        if isinstance(tok, str) and tok:
            return tok
        return None

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def search(self, image_path: str, cursor: Optional[str] = None) -> ProviderPage:
        # KEY-GATING (mandatory) ----------------------------------------
        if not self.is_configured():
            return self._not_configured_page()

        # Google Lens needs a publicly fetchable image URL.
        public_url = self._public_image_url(image_path)
        if not public_url:
            return self._error_page(
                "google_lens needs a public image URL "
                "(set OMNI_PUBLIC_BASE_URL so the query face is reachable)"
            )

        params = {
            "engine": self.engine,
            "url": public_url,
            "api_key": self.api_key,
        }
        page_token = self._decode_cursor(cursor)
        if page_token:
            params["page_token"] = page_token

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

        # Visual matches are the primary public-image hits. We also tolerate the
        # older/alternate key names so a SerpApi schema tweak degrades to fewer
        # results rather than an exception.
        raw_hits = (
            payload.get("visual_matches")
            or payload.get("image_results")
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

        next_cursor = self._encode_cursor(self._extract_next_token(payload))

        return {
            "results": results,
            "next_cursor": next_cursor,
            "note": None,  # clean success
        }
