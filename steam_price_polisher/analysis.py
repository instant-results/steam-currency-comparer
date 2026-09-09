"""Resumable wishlist analysis orchestration independent from the CLI."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from .comparison import compare_game
from .configuration import ComparisonConfig, RegionConfig
from .models import (
    GameComparison,
    PriceStatus,
    SkipCategory,
    SkippedGame,
    WishlistItem,
)
from .price_service import CachedPriceService, PriceLookup
from .steam_access import SteamAccessError


@dataclass(frozen=True)
class AnalysisProgress:
    index: int
    total: int
    app_id: str
    name: str
    comparison: GameComparison | None
    skipped: SkippedGame | None
    cache_hits: int
    stale_cache_hits: int
    live_requests: int

    @property
    def status(self) -> str:
        if self.comparison is not None:
            return "fair" if self.comparison.is_fair else "expensive"
        if self.skipped is not None:
            return self.skipped.reason
        raise AssertionError("progress has neither a comparison nor a skipped result")

    @property
    def source_summary(self) -> str:
        parts: list[str] = []
        if self.cache_hits:
            parts.append(f"cache {self.cache_hits}")
        if self.stale_cache_hits:
            parts.append(f"stale {self.stale_cache_hits}")
        if self.live_requests:
            parts.append(f"live {self.live_requests}")
        return ", ".join(parts)


def deduplicate_wishlist(items: Iterable[WishlistItem]) -> tuple[WishlistItem, ...]:
    unique: dict[str, WishlistItem] = {}
    for item in items:
        existing = unique.get(item.app_id)
        if existing is None or (existing.name is None and item.name is not None):
            unique[item.app_id] = item
    return tuple(unique.values())


class AnalysisRunner:
    def __init__(
        self,
        price_service: CachedPriceService,
        *,
        home: RegionConfig,
        alternatives: Sequence[RegionConfig],
    ) -> None:
        config = ComparisonConfig(home=home, alternatives=tuple(alternatives))
        self._price_service = price_service
        self._home = config.home
        self._alternatives = config.alternatives

    def run(
        self,
        wishlist: Sequence[WishlistItem],
        rates_to_home: Mapping[str, float],
    ) -> Iterator[AnalysisProgress]:
        total = len(wishlist)
        for index, item in enumerate(wishlist, start=1):
            yield self._analyze_game(index, total, item, rates_to_home)

    def _analyze_game(
        self,
        index: int,
        total: int,
        item: WishlistItem,
        rates_to_home: Mapping[str, float],
    ) -> AnalysisProgress:
        lookups: list[PriceLookup] = []
        display_name = item.name or f"App {item.app_id}"

        try:
            home_lookup = self._price_service.get_regional_price(
                item.app_id,
                self._home.region,
                self._home.currency,
            )
        except SteamAccessError as exc:
            return self._skipped_from_error(
                index, total, item.app_id, display_name, exc, lookups
            )
        lookups.append(home_lookup)

        home_result = home_lookup.result
        if home_result.game_name:
            display_name = home_result.game_name
        if home_result.status is not PriceStatus.AVAILABLE:
            return self._skipped(
                index,
                total,
                item.app_id,
                display_name,
                home_result.detail or f"No {self._home.currency} regional price.",
                self._category_for_status(home_result.status),
                self._home.region,
                False,
                lookups,
            )

        alternative_prices = []
        for alternative in self._alternatives:
            try:
                lookup = self._price_service.get_regional_price(
                    item.app_id,
                    alternative.region,
                    alternative.currency,
                )
            except SteamAccessError as exc:
                return self._skipped_from_error(
                    index, total, item.app_id, display_name, exc, lookups
                )
            lookups.append(lookup)
            if lookup.result.status is not PriceStatus.AVAILABLE:
                return self._skipped(
                    index,
                    total,
                    item.app_id,
                    display_name,
                    lookup.result.detail
                    or f"No {alternative.currency} regional price.",
                    self._category_for_status(lookup.result.status),
                    alternative.region,
                    False,
                    lookups,
                )
            alternative_prices.append(lookup.result.price)

        comparison = compare_game(
            item.app_id,
            display_name,
            home_result.price,
            alternative_prices,
            rates_to_home,
        )
        cache_hits, stale_hits, live_requests = self._source_counts(lookups)
        return AnalysisProgress(
            index,
            total,
            item.app_id,
            display_name,
            comparison,
            None,
            cache_hits,
            stale_hits,
            live_requests,
        )

    def _skipped(
        self,
        index: int,
        total: int,
        app_id: str,
        name: str,
        reason: str,
        category: SkipCategory,
        region: str | None,
        retryable: bool,
        lookups: Sequence[PriceLookup],
    ) -> AnalysisProgress:
        cache_hits, stale_hits, live_requests = self._source_counts(lookups)
        return AnalysisProgress(
            index,
            total,
            app_id,
            name,
            None,
            SkippedGame(app_id, name, reason, category, region, retryable),
            cache_hits,
            stale_hits,
            live_requests,
        )

    def _skipped_from_error(
        self,
        index: int,
        total: int,
        app_id: str,
        name: str,
        error: SteamAccessError,
        lookups: Sequence[PriceLookup],
    ) -> AnalysisProgress:
        return self._skipped(
            index,
            total,
            app_id,
            name,
            str(error),
            error.category,
            error.region,
            error.retryable,
            lookups,
        )

    @staticmethod
    def _category_for_status(status: PriceStatus) -> SkipCategory:
        if status is PriceStatus.NO_REGIONAL_PRICE:
            return SkipCategory.NO_REGIONAL_PRICE
        if status is PriceStatus.APP_UNAVAILABLE:
            return SkipCategory.APP_UNAVAILABLE
        raise ValueError(f"Available status cannot be converted to a skip category: {status}")

    @staticmethod
    def _source_counts(lookups: Sequence[PriceLookup]) -> tuple[int, int, int]:
        return (
            sum(lookup.source == "cache" for lookup in lookups),
            sum(lookup.source == "stale cache" for lookup in lookups),
            sum(lookup.source == "live" for lookup in lookups),
        )
