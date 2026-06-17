"""
backend/providers/yandex.py

Yandex reverse-image-search provider (browser automation via Scrapling, no API key).

Flow (see base.Provider): open public Yandex Images, upload the cropped query-face
JPEG via the "search by image" file input, wait for the CBIR results, and scrape
up to 20 public hits — the "sites that contain this image" entries (source page
URL + title + preview thumbnail) plus similar-image previews.

Honesty/safety: never fabricates; detects CAPTCHA/anti-bot and reports "blocked";
no proxies, no CAPTCHA bypass, capped at 20. Yandex is the most automation-tolerant
of the three engines and tends to be the best for faces.
"""

from __future__ import annotations

from .base import Provider, ProviderPage, ProviderResult
from ._browser import absolutize, dismiss_consent, looks_blocked, run_action, try_upload

_UPLOAD_URL = "https://yandex.com/images/"
_RESULT_SELECTOR = ".CbirSites-Item, a.Thumb, [class*='CbirSites']"
_FILE_SELECTORS = ("input[type=file]",)
_REVEAL_SELECTORS = (
    "button.input__cbir-button",
    "button[aria-label*='image' i]",
    ".websearch__cbir-button",
    ".input__button",
)

_EXTRACT_JS = r"""
() => {
  const out = []; const pushed = new Set();
  const add = (image_url, thumbnail_url, page_url, page_title) => {
    if (!image_url || pushed.has(image_url)) return;
    pushed.add(image_url);
    out.push({ image_url, thumbnail_url: thumbnail_url || null,
               page_url: page_url || null, page_title: page_title || null });
  };
  // "Sites that contain this image" — real source pages (best signal).
  document.querySelectorAll('.CbirSites-Item').forEach(item => {
    const a = item.querySelector('a.CbirSites-ItemTitle, .CbirSites-ItemTitle a, a[href]');
    const img = item.querySelector('img');
    const thumb = img ? (img.src || img.getAttribute('data-src')) : null;
    add(thumb, thumb, a ? a.href : null, a ? (a.textContent || '').trim() : null);
  });
  // Similar-image / object thumbnails: anchors with a Thumb class wrapping an img
  // (each is a Yandex-proxied preview of a matched public image + its source link).
  document.querySelectorAll("a.Thumb, a[class*='Thumb']").forEach(a => {
    const img = a.querySelector('img');
    const thumb = img ? (img.src || img.getAttribute('data-src')) : null;
    if (!thumb) return;
    add(thumb, thumb, a.href || null, img.alt ? img.alt.trim() : null);
  });
  return out.slice(0, 60);
}
"""


class YandexProvider(Provider):
    name = "yandex"

    def _scrape(self, image_path: str) -> ProviderPage:
        def action(page, cap):
            if looks_blocked(page):
                cap["blocked"] = True
                return
            if not try_upload(page, image_path, _FILE_SELECTORS, _REVEAL_SELECTORS):
                cap["blocked"] = looks_blocked(page)
                cap["no_upload"] = True
                return
            # Results load async behind a cookie banner; dismiss it then wait.
            page.wait_for_timeout(2000)
            dismiss_consent(page)
            try:
                page.wait_for_selector(_RESULT_SELECTOR, timeout=20000)
            except Exception:
                pass
            # The similar-images grid is lazy-loaded; scroll in steps so more
            # thumbnails actually fetch their src before we harvest.
            for _ in range(5):
                page.mouse.wheel(0, 3500)
                page.wait_for_timeout(1200)
            if looks_blocked(page):
                cap["blocked"] = True
                return
            cap["base_url"] = page.url
            cap["raw"] = page.evaluate(_EXTRACT_JS) or []

        try:
            cap = run_action(_UPLOAD_URL, action)
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
