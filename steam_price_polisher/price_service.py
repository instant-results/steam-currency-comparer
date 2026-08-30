"""Cache-aware regional price retrieval."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .cache import SQLiteCache
from .models import PriceStatus, RegionalPriceResult
from .steam_access import SteamTemporaryError


class LiveRegionalPriceProvider(Protocol):
    def get_regional_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
    ) -> RegionalPriceResult:
        """Retrieve one regional price from its authoritative source."""


@dataclass(frozen=True)
class PriceLookup:
    result: RegionalPriceResult
    source: str


class CachedPriceService:
    def __init__(
        self,
        live_provider: LiveRegionalPriceProvider,
        cache: SQLiteCache,
        *,
        price_ttl: float = 12 * 60 * 60,
        missing_ttl: float = 60 * 60,
        unavailable_ttl: float = 6 * 60 * 60,
        clock: Callable[[], float] = time.time,
        use_stale_on_error: bool = True,
    ) -> None:
        self._live_provider = live_provider
        self._cache = cache
        self._price_ttl = price_ttl
        self._missing_ttl = missing_ttl
        self._unavailable_ttl = unavailable_ttl
        self._clock = clock
        self._use_stale_on_error = use_stale_on_error

    def get_regional_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
    ) -> PriceLookup:
        cached = self._cache.get_price(app_id, region, expected_currency)
        if cached is not None:
            ttl = {
                PriceStatus.AVAILABLE: self._price_ttl,
                PriceStatus.NO_REGIONAL_PRICE: self._missing_ttl,
                PriceStatus.APP_UNAVAILABLE: self._unavailable_ttl,
            }[cached.result.status]
            if self._clock() - cached.fetched_at <= ttl:
                return PriceLookup(cached.result, "cache")

        try:
            live = self._live_provider.get_regional_price(
                app_id,
                region,
                expected_currency,
            )
        except SteamTemporaryError:
            if cached is not None and self._use_stale_on_error:
                return PriceLookup(cached.result, "stale cache")
            raise

        self._cache.put_price(app_id, region, expected_currency, live)
        return PriceLookup(live, "live")
