"""
backend/providers/yandex.py

Yandex reverse-image-search provider (browser automation via Scrapling, no API key).

Flow (see base.Provider): open public Yandex Images, upload the cropped query-face
JPEG, then navigate to Yandex's dedicated "similar images" view
(``cbir_page=similar``) which returns a large grid of visually/face-similar public
images (often 100-400). We scroll to load the grid and scrape the
``.ImagesContentImage`` cards (thumbnail + source link), capped at
``result_limit``. Downstream re-embeds each and keeps only real face matches.

Honesty/safety: never fabricates; detects CAPTCHA/anti-bot and reports "blocked";
no proxies, no CAPTCHA bypass. Yandex is the most automation-tolerant engine and
its similar-images grid is by far the best free source of many face matches.
"""

from __future__ import annotations

import re

from .base import Provider, ProviderPage, ProviderResult
from ._browser import absolutize, dismiss_consent, looks_blocked, run_action, try_upload

_UPLOAD_URL = "https://yandex.com/images/"
_FILE_SELECTORS = ("input[type=file]",)
_REVEAL_SELECTORS = (
    "button.input__cbir-button",
    "button[aria-label*='image' i]",
    ".websearch__cbir-button",
    ".input__button",
)

# The similar-images grid. Each card carries a thumbnail (an avatars.mds preview
# of a matched public image) and a link to its source. This is where the volume
# of face matches lives.
_EXTRACT_JS = r"""
() => {
  const out = []; const seen = new Set();
  // Each tile's cover link carries the REAL source image URL in its `img_url`
  // query param (e.g. upload.wikimedia.org/..., scontent.cdninstagram.com/...,
  // media.licdn.com/...). The thumbnail (avatars.mds) is what we embed; the
  // img_url domain is the true source we display + filter on. The img `alt` is
  // the source page title.
  document.querySelectorAll('.ImagesContentImage').forEach(card => {
    const im = card.querySelector('img');
    const a = card.querySelector('a.ImagesContentImage-Cover, a[href]');
    const thumb = im ? (im.src || im.getAttribute('data-src')) : null;
    if (!thumb || seen.has(thumb)) return;
    seen.add(thumb);
    let source = null;
    if (a && a.href) {
      try { source = new URL(a.href, location.origin).searchParams.get('img_url'); }
      catch (e) {}
    }
    out.push({
      image_url: thumb,
      thumbnail_url: thumb,
      page_url: source || null,                 // real source image URL
      page_title: im && im.alt ? im.alt.trim() : null,
    });
  });
  // Fallback: "sites that contain this image" (real source pages).
  document.querySelectorAll('.CbirSites-Item').forEach(item => {
    const a = item.querySelector('a.CbirSites-ItemTitle, .CbirSites-ItemTitle a, a[href]');
    const im = item.querySelector('img');
    const src = im ? (im.src || im.getAttribute('data-src')) : null;
    if (!src || seen.has(src)) return;
    seen.add(src);
    out.push({ image_url: src, thumbnail_url: src,
               page_url: a ? a.href : null,
               page_title: a ? (a.textContent || '').trim() : null });
  });
  return out.slice(0, 120);
}
"""


class YandexProvider(Provider):
    name = "yandex"
    # Yandex's similar grid is rich; allow more than the shared default so we can
    # surface many face matches (downstream filtering trims non-faces/strangers).
    # Capped for sane processing time on small hardware (each is re-embedded).
    # buffalo_s embeds at ~0.25s each, so a larger batch is affordable.
    result_limit = 80

    def _scrape(self, image_path: str) -> ProviderPage:
        def action(page, cap):
            if looks_blocked(page):
                cap["blocked"] = True
                return
            if not try_upload(page, image_path, _FILE_SELECTORS, _REVEAL_SELECTORS):
                cap["blocked"] = looks_blocked(page)
                cap["no_upload"] = True
                return
            page.wait_for_timeout(2000)
            dismiss_consent(page)
            page.wait_for_timeout(1500)
            # Jump to the dedicated similar-images view (the big grid).
            try:
                u = page.url
                su = (
                    re.sub(r"cbir_page=[^&]+", "cbir_page=similar", u)
                    if "cbir_page=" in u
                    else u + "&cbir_page=similar"
                )
                page.goto(su, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
            except Exception:
                pass
            # Lazy-loaded grid: scroll in steps so thumbnails fetch their src.
            # More scroll iterations load more of the (very large) similar grid.
            for _ in range(14):
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(650)
            if looks_blocked(page):
                cap["blocked"] = True
                return
            cap["base_url"] = page.url
            cap["raw"] = page.evaluate(_EXTRACT_JS) or []

        try:
            cap = run_action(_UPLOAD_URL, action, nav_timeout_ms=60000)
        except Exception as exc:
            return self._error_page(f"browser error ({type(exc).__name__})")

        if cap.get("blocked"):
            return self._blocked_page()
        if cap.get("no_upload"):
            return self._error_page("could not start image search (upload UI changed)")
        if cap.get("error") and not cap.get("raw"):
            return self._error_page(f"page error ({cap['error']})")

        base_url = cap.get("base_url") or _UPLOAD_URL
        results: list[ProviderResult] = []
        for hit in cap.get("raw", []):
            image_url = absolutize(base_url, hit.get("image_url"))
            if not image_url:
                continue
            results.append(
                {
                    "image_url": image_url,
                    "thumbnail_url": absolutize(base_url, hit.get("thumbnail_url")) or image_url,
                    "page_url": absolutize(base_url, hit.get("page_url")),
                    "page_title": hit.get("page_title") or None,
                    "provider": self.name,
                }
            )
        return self._ok_page(results)
