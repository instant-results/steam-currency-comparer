"""Resumable wishlist analysis orchestration independent from the CLI."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace

from .comparison import compare_game
from .configuration import ComparisonConfig, RegionConfig
from .models import (
    GameComparison,
    PriceStatus,
    SkipCategory,
    SkippedGame,
    WishlistItem,
    StorePrice,
)
from .price_service import CachedPriceService, PriceLookup
from .steam_access import SteamAccessError

WISHLIST_ORDERS = frozenset({"priority", "date_added", "name"})


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
    is_free: bool = False
    developers: tuple[str, ...] | None = None
    publishers: tuple[str, ...] | None = None
    best_offer_comparison: GameComparison | None = None
    best_offers: dict | None = None
    metadata_source: str | None = None

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
        if existing is None:
            unique[item.app_id] = item
        else:
            unique[item.app_id] = WishlistItem(
                app_id=item.app_id,
                name=existing.name if existing.name is not None else item.name,
                date_added=(existing.date_added if existing.date_added is not None else item.date_added),
                priority=existing.priority if existing.priority is not None else item.priority,
            )
    return tuple(unique.values())


def order_wishlist_items(
    items: Sequence[WishlistItem], order: str
) -> tuple[WishlistItem, ...]:
    """Order items using metadata already supplied by Steam."""
    if order not in WISHLIST_ORDERS:
        raise ValueError(f"Unsupported wishlist order: {order!r}")
    indexed = tuple(enumerate(items))
    if order == "priority":
        key = lambda pair: (
            pair[1].priority is None,
            pair[1].priority if pair[1].priority is not None else 0,
            pair[0],
        )
    elif order == "date_added":
        key = lambda pair: (
            pair[1].date_added is None,
            -(pair[1].date_added if pair[1].date_added is not None else 0),
            pair[0],
        )
    else:
        key = lambda pair: (
            pair[1].name is None,
            (pair[1].name or "").casefold(),
            pair[0],
        )
    return tuple(item for _, item in sorted(indexed, key=key))


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
        *,
        order: str = "priority",
    ) -> Iterator[AnalysisProgress]:
        if hasattr(self._price_service, "prepare"):
            yield from self._run_batched(wishlist, rates_to_home, order)
            return
        prepared = self._prepare_wishlist(wishlist, order)
        total = len(prepared)
        for index, (item, home_lookup, home_error) in enumerate(prepared, start=1):
            yield self._analyze_game(
                index,
                total,
                item,
                rates_to_home,
                home_lookup=home_lookup,
                home_error=home_error,
            )

    def _run_batched(self, wishlist, rates, order):
        service = self._price_service
        regions = (self._home, *self._alternatives)
        prefix_requests = 0
        wishlist = deduplicate_wishlist(wishlist)
        if order == "name":
            started = service.provider.attempts
            service.prepare_metadata([item.app_id for item in wishlist], self._home)
            prefix_requests = service.provider.attempts - started
            wishlist = tuple(replace(item, name=service.metadata.get((item.app_id, self._home.region), {}).get("name") or item.name)
                             for item in wishlist)
        ordered = order_wishlist_items(wishlist, order)
        for offset in range(0, len(ordered), service.window_size):
            window = ordered[offset:offset + service.window_size]
            service.prepare([item.app_id for item in window], regions)
            requests = service.window_requests + prefix_requests
            prefix_requests = 0
            for position, item in enumerate(window):
                service.provider.check()
                progress = self._analyze_game(offset + position + 1, len(ordered), item, rates)
                offers = service.best_offers(item.app_id, regions)
                for region in regions:
                    offer = offers[region.region]
                    if offer.get("price"):
                        factor = 1 if region.region == self._home.region else rates[region.currency]
                        offer.update(rate_to_home=factor, amount_in_home=offer["price"]["amount"] * factor)
                best = None
                if all(offers[r.region].get("status") == "available" for r in regions):
                    prices = [StorePrice(**offers[r.region]["price"]) for r in regions]
                    best = compare_game(item.app_id, progress.name, prices[0], prices[1:], rates)
                metadata = next((service.metadata.get((item.app_id, r.region)) for r in regions
                                 if service.metadata.get((item.app_id, r.region), {}).get("name")), {})
                # Attribute shared physical requests once, to the window's first row.
                yield replace(progress, live_requests=requests if position == 0 else 0,
                    best_offer_comparison=best, best_offers=offers,
                    metadata_source=metadata.get("source"),
                    name=metadata.get("name") or progress.name,
                    developers=tuple(metadata["developers"]) if metadata else progress.developers,
                    publishers=tuple(metadata["publishers"]) if metadata else progress.publishers)

    def _prepare_wishlist(
        self,
        wishlist: Sequence[WishlistItem],
        order: str,
    ) -> tuple[tuple[WishlistItem, PriceLookup | None, SteamAccessError | None], ...]:
        if order not in WISHLIST_ORDERS:
            raise ValueError(f"Unsupported wishlist order: {order!r}")
        if order != "name" or all(item.name is not None for item in wishlist):
            return tuple(
                (item, None, None)
                for item in order_wishlist_items(wishlist, order)
            )

        prepared: list[tuple[WishlistItem, PriceLookup | None, SteamAccessError | None]] = []
        for item in wishlist:
            if item.name is not None:
                prepared.append((item, None, None))
                continue
            try:
                lookup = self._price_service.get_regional_price(
                    item.app_id,
                    self._home.region,
                    self._home.currency,
                )
            except SteamAccessError as exc:
                if exc.category is SkipCategory.NETWORK_ACCESS_DENIED:
                    # Alphabetical prefetch must not repeat a server-wide denial for every game.
                    raise
                prepared.append((item, None, exc))
                continue
            display_name = lookup.result.game_name or f"App {item.app_id}"
            prepared.append((replace(item, name=display_name), lookup, None))
        return tuple(
            sorted(
                prepared,
                key=lambda entry: (entry[0].name or "").casefold(),
            )
        )

    def _analyze_game(
        self,
        index: int,
        total: int,
        item: WishlistItem,
        rates_to_home: Mapping[str, float],
        *,
        home_lookup: PriceLookup | None = None,
        home_error: SteamAccessError | None = None,
    ) -> AnalysisProgress:
        lookups: list[PriceLookup] = []
        display_name = item.name or f"App {item.app_id}"

        if home_error is not None:
            return self._skipped_from_error(
                index, total, item.app_id, display_name, home_error, lookups
            )
        if home_lookup is None:
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
            alternative_prices.append(replace(lookup.result.price, source=lookup.source))

        comparison = compare_game(
            item.app_id,
            display_name,
            replace(home_result.price, source=home_lookup.source),
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
            developers=next((lookup.result.developers for lookup in lookups if lookup.result.developers is not None), None),
            publishers=next((lookup.result.publishers for lookup in lookups if lookup.result.publishers is not None), None),
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
            any(lookup.result.is_free is True for lookup in lookups),
            next((lookup.result.developers for lookup in lookups if lookup.result.developers is not None), None),
            next((lookup.result.publishers for lookup in lookups if lookup.result.publishers is not None), None),
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
