"""
backend/providers/bing.py

Bing Visual Search provider (browser automation via Scrapling, no API key).

Flow (see base.Provider): open Bing Images, open "search by image", upload the
cropped query-face JPEG, wait for the visual-search results, and scrape up to 20
public hits. Bing exposes clean per-image metadata on its image cards
(``a.iusc`` carries an ``m`` attribute JSON with murl/turl/purl/t), which we
parse; a generic card fallback covers layout drift.

Honesty/safety: never fabricates; detects CAPTCHA/anti-bot and reports "blocked";
no proxies, no CAPTCHA bypass, capped at 20.
"""

from __future__ import annotations

from .base import Provider, ProviderPage, ProviderResult
from ._browser import absolutize, looks_blocked, run_action, try_upload

_IMAGES_URL = "https://www.bing.com/images"
_RESULT_SELECTOR = "a.iusc, .mc_vtvc, .richImage"
_FILE_SELECTORS = ("input[type=file]",)
_REVEAL_SELECTORS = ("#sb_sbip", "#sb_sbi", ".sbi_camera", "[aria-label*='image' i]")

_EXTRACT_JS = r"""
() => {
  const out = []; const pushed = new Set();
  const add = (image_url, thumbnail_url, page_url, page_title) => {
    if (!image_url || pushed.has(image_url)) return;
    pushed.add(image_url);
    out.push({ image_url, thumbnail_url: thumbnail_url || null,
               page_url: page_url || null, page_title: page_title || null });
  };
  // Cards with structured metadata (best signal).
  document.querySelectorAll('a.iusc').forEach(a => {
    const m = a.getAttribute('m'); if (!m) return;
    try { const d = JSON.parse(m); add(d.murl || d.turl, d.turl || d.murl, d.purl, d.t || null); }
    catch (e) {}
  });
  // Visual-search "similar images" / "pages" card fallback.
  document.querySelectorAll('.mc_vtvc, .richImage, .imgpt').forEach(card => {
    const img = card.querySelector('img');
    const a = card.querySelector('a[href]');
    const thumb = img ? (img.src || img.getAttribute('data-src')) : null;
    add(thumb, thumb, a ? a.href : null, img && img.alt ? img.alt.trim() : null);
  });
  return out.slice(0, 60);
}
"""


class BingProvider(Provider):
    name = "bing"

    def _scrape(self, image_path: str) -> ProviderPage:
        def action(page, cap):
            if looks_blocked(page):
                cap["blocked"] = True
                return
            if not try_upload(page, image_path, _FILE_SELECTORS, _REVEAL_SELECTORS):
                cap["blocked"] = looks_blocked(page)
                cap["no_upload"] = True
                return
            try:
                page.wait_for_selector(_RESULT_SELECTOR, timeout=20000)
            except Exception:
                pass
            if looks_blocked(page):
                cap["blocked"] = True
                return
            cap["base_url"] = page.url
            cap["raw"] = page.evaluate(_EXTRACT_JS) or []

        try:
            cap = run_action(_IMAGES_URL, action)
        except Exception as exc:
            return self._error_page(f"browser error ({type(exc).__name__})")

        if cap.get("blocked"):
            return self._blocked_page()
        if cap.get("no_upload"):
            return self._error_page("could not start image search (upload UI changed)")
        if cap.get("error") and not cap.get("raw"):
            return self._error_page(f"page error ({cap['error']})")

        base_url = cap.get("base_url") or _IMAGES_URL
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
