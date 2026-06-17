"""
backend/providers/google_lens.py

Google Lens reverse-image-search provider (browser automation via Scrapling, no
API key).

Flow (see base.Provider): open the Google Lens upload page, dismiss any cookie/
consent interstitial, upload the cropped query-face JPEG, wait for visual matches,
and scrape up to 20 public hits (source page link + preview thumbnail).

Reality check: Google Lens has the most obfuscated DOM and the most aggressive
anti-bot of the three engines — it frequently shows a consent wall or CAPTCHA to
automated browsers. When that happens we report "blocked" and return nothing
rather than trying to bypass it. Yandex/Bing are the more reliable providers.

Honesty/safety: never fabricates; no proxies, no CAPTCHA bypass, capped at 20.
"""

from __future__ import annotations

from .base import Provider, ProviderPage, ProviderResult
from ._browser import absolutize, looks_blocked, run_action, try_upload

_UPLOAD_URL = "https://lens.google.com/upload"
_FILE_SELECTORS = ("input[type=file]",)
_REVEAL_SELECTORS = ("[aria-label*='upload' i]", "[aria-label*='image' i]")
_CONSENT_SELECTORS = (
    "button[aria-label*='Accept all' i]",
    "button[aria-label*='Reject all' i]",
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
    "#L2AGLb",
)

# Result class names are randomized, so scan anchors wrapping an image that point
# off-site, collecting the preview img + (unwrapped) source link.
_EXTRACT_JS = r"""
() => {
  const out = []; const pushed = new Set();
  document.querySelectorAll('a[href] img').forEach(node => {
    const a = node.closest('a[href]'); if (!a) return;
    let href = a.href || '';
    try { const u = new URL(href);
      const real = u.searchParams.get('imgurl') || u.searchParams.get('url') || u.searchParams.get('q');
      if (real) href = real;
    } catch (e) {}
    const img = node.src || node.getAttribute('data-src');
    if (!img || pushed.has(img)) return;
    pushed.add(img);
    const title = (node.alt || a.getAttribute('aria-label') || a.textContent || '').trim();
    out.push({ image_url: img, thumbnail_url: img, page_url: href, page_title: title || null });
  });
  return out.slice(0, 60);
}
"""


class GoogleLensProvider(Provider):
    name = "google_lens"

    def _scrape(self, image_path: str) -> ProviderPage:
        def action(page, cap):
            for sel in _CONSENT_SELECTORS:
                try:
                    page.click(sel, timeout=2000)
                    break
                except Exception:
                    continue
            if looks_blocked(page):
                cap["blocked"] = True
                return
            if not try_upload(page, image_path, _FILE_SELECTORS, _REVEAL_SELECTORS):
                cap["blocked"] = looks_blocked(page)
                cap["no_upload"] = True
                return
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
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
            return self._error_page("could not start image search (blocked or UI changed)")
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
