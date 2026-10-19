"""Cache-aware regional price retrieval."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .cache import SQLiteCache
from .models import PriceStatus, RegionalPriceResult
from .steam_access import SteamTemporaryError
from .event_log import emit


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
        require_sale_metadata: bool = False,
        sale_ttl: float = 15 * 60,
        require_credits: bool = False,
    ) -> None:
        self._live_provider = live_provider
        self._cache = cache
        self._price_ttl = price_ttl
        self._missing_ttl = missing_ttl
        self._unavailable_ttl = unavailable_ttl
        self._clock = clock
        self._use_stale_on_error = use_stale_on_error
        self._require_sale_metadata = require_sale_metadata
        self._sale_ttl = sale_ttl
        self._require_credits = require_credits

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
            price = cached.result.price
            metadata_missing = self._require_sale_metadata and price is not None and (
                price.base_amount is None or price.discount_percent is None
            )
            # Old missing-price cache entries cannot distinguish free products.
            metadata_missing |= self._require_sale_metadata and (
                cached.result.status is PriceStatus.NO_REGIONAL_PRICE and cached.result.is_free is None
            )
            metadata_missing |= self._require_credits and cached.result.status is not PriceStatus.APP_UNAVAILABLE and (
                cached.result.developers is None or cached.result.publishers is None
            )
            if price is not None and ((price.discount_percent or 0) > 0 or
                                      price.base_amount is not None and price.amount < price.base_amount):
                ttl = min(ttl, self._sale_ttl)
            if not metadata_missing and self._clock() - cached.fetched_at <= ttl:
                emit("cache_access", cache_kind="price", source="cache")
                return PriceLookup(cached.result, "cache")

        try:
            live = self._live_provider.get_regional_price(
                app_id,
                region,
                expected_currency,
            )
        except SteamTemporaryError:
            if cached is not None and self._use_stale_on_error:
                emit("cache_access", cache_kind="price", source="stale cache")
                return PriceLookup(cached.result, "stale cache")
            raise

        self._cache.put_price(app_id, region, expected_currency, live)
        emit("cache_access", cache_kind="price", source="live")
        return PriceLookup(live, "live")
