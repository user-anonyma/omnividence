"""
backend/providers/__init__.py

Provider registry for Omnividence reverse-image-search.

Exposes :func:`get_providers`, the single place the route obtains the ordered
list of providers. Every provider shares the same SerpApi key (``SERPAPI_KEY``)
and the same :class:`~backend.providers.base.Provider` interface. Un-configured
providers (no key) cleanly return ``[]`` plus an honest "provider not configured"
note — they are never silently dropped, so the route can report their state.

Order matters (MVP enables google_lens first):
    [GoogleLensProvider, YandexProvider, BingProvider]
"""

from __future__ import annotations

from typing import Optional

from .base import Provider, ProviderPage, ProviderResult
from .bing import BingProvider
from .google_lens import GoogleLensProvider
from .yandex import YandexProvider

# Provider classes in route order (MVP: google_lens first). The route may select
# a subset by .name (e.g. ["google_lens", "yandex", "bing"]).
PROVIDER_CLASSES: list[type[Provider]] = [
    GoogleLensProvider,
    YandexProvider,
    BingProvider,
]

# Convenience: the canonical provider names in order.
PROVIDER_NAMES: list[str] = [cls.name for cls in PROVIDER_CLASSES]


def get_providers(api_key: Optional[str]) -> list[Provider]:
    """Instantiate every provider with the shared SerpApi key, in route order.

    Returns ``[GoogleLensProvider(api_key), YandexProvider(api_key),
    BingProvider(api_key)]``. The route calls ``.search`` on each; un-configured
    ones cleanly return ``[]`` + a note (they are NOT filtered out here so the
    route can honestly surface the not-configured state).
    """
    return [cls(api_key) for cls in PROVIDER_CLASSES]


def get_providers_by_name(
    api_key: Optional[str], names: Optional[list[str]] = None
) -> list[Provider]:
    """Like :func:`get_providers` but optionally filtered to a subset of names.

    ``names=None`` (or empty) => all providers in route order. Unknown names are
    ignored. Order follows :data:`PROVIDER_CLASSES`, not the order in ``names``,
    so results stay deterministic regardless of how the caller listed them.
    """
    providers = get_providers(api_key)
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
