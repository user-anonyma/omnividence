"""
backend/providers/__init__.py

Provider registry for Omnividence reverse-image-search.

Exposes :func:`get_providers`, the single place the route obtains the ordered
list of providers. Providers drive the REAL public reverse-image pages with a
headless Chromium (Playwright) — no API keys. A provider that can't run (browser
unavailable / blocked by CAPTCHA / no hits) cleanly returns ``[]`` plus an honest
note; it is never silently dropped, so the route can report its state.

Order (MVP enables the most automation-tolerant engine first):
    [YandexProvider, BingProvider, GoogleLensProvider]
"""

from __future__ import annotations

from typing import Optional

from .base import Provider, ProviderPage, ProviderResult
from .bing import BingProvider
from .google_lens import GoogleLensProvider
from .yandex import YandexProvider

# Provider classes in route order. Yandex is the most reliable for faces; Google
# Lens is the most bot-hostile, so it goes last.
PROVIDER_CLASSES: list[type[Provider]] = [
    YandexProvider,
    BingProvider,
    GoogleLensProvider,
]

# Convenience: the canonical provider names in order.
PROVIDER_NAMES: list[str] = [cls.name for cls in PROVIDER_CLASSES]


def get_providers(api_key: Optional[str] = None) -> list[Provider]:
    """Instantiate every provider in route order.

    These are browser-automation providers and take no API key; the optional
    ``api_key`` arg is accepted (and ignored) only so existing call sites stay
    stable. The route calls ``.search`` on each; providers that can't run cleanly
    return ``[]`` + a note (they are NOT filtered out here so the route can
    honestly surface the unavailable/blocked state).
    """
    return [cls() for cls in PROVIDER_CLASSES]


def get_providers_by_name(
    api_key: Optional[str] = None, names: Optional[list[str]] = None
) -> list[Provider]:
    """Like :func:`get_providers` but optionally filtered to a subset of names.

    ``names=None`` (or empty) => all providers in route order. Unknown names are
    ignored. Order follows :data:`PROVIDER_CLASSES`, not the order in ``names``,
    so results stay deterministic regardless of how the caller listed them.
    """
    providers = get_providers()
    if not names:
        return providers
    wanted = {n.strip() for n in names if n and n.strip()}
    if not wanted:
        return providers
    return [p for p in providers if p.name in wanted]


__all__ = [
    "Provider",
    "ProviderPage",
    "ProviderResult",
    "GoogleLensProvider",
    "YandexProvider",
    "BingProvider",
    "PROVIDER_CLASSES",
    "PROVIDER_NAMES",
    "get_providers",
    "get_providers_by_name",
]
