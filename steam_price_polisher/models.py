"""Shared data structures used across the application layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class WishlistItem:
    app_id: str
    name: str | None = None
    date_added: int | None = None
    priority: int | None = None


class WishlistFailure(str, Enum):
    TLS = "tls"
    REQUEST = "request"
    INVALID_RESPONSE = "invalid_response"
    VANITY = "vanity"


@dataclass(frozen=True)
class WishlistResult:
    items: tuple[WishlistItem, ...]
    source: str
    warnings: tuple[str, ...] = ()
    failure: WishlistFailure | None = None


@dataclass(frozen=True)
class StorePrice:
    region: str
    currency: str
    amount: float
    base_amount: float | None = None
    discount_percent: int | None = None
    source: str | None = None


class PriceStatus(str, Enum):
    AVAILABLE = "available"
    NO_REGIONAL_PRICE = "no_regional_price"
    APP_UNAVAILABLE = "app_unavailable"


@dataclass(frozen=True)
class RegionalPriceResult:
    status: PriceStatus
    price: StorePrice | None = None
    game_name: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.status is PriceStatus.AVAILABLE and self.price is None:
            raise ValueError("An available result requires a price")
        if self.status is not PriceStatus.AVAILABLE and self.price is not None:
            raise ValueError("A non-available result cannot contain a price")

    @classmethod
    def available(
        cls,
        price: StorePrice,
        game_name: str | None,
    ) -> RegionalPriceResult:
        return cls(PriceStatus.AVAILABLE, price, game_name)

    @classmethod
    def no_regional_price(
        cls,
        game_name: str | None,
        detail: str | None = None,
    ) -> RegionalPriceResult:
        return cls(PriceStatus.NO_REGIONAL_PRICE, None, game_name, detail)

    @classmethod
    def app_unavailable(
        cls,
        detail: str | None = None,
    ) -> RegionalPriceResult:
        return cls(PriceStatus.APP_UNAVAILABLE, None, None, detail)


@dataclass(frozen=True)
class ConvertedPrice:
    region: str
    currency: str
    original_amount: float
    rate_to_home: float
    amount_in_home: float
    base_amount: float | None = None
    discount_percent: int | None = None
    source: str | None = None


@dataclass(frozen=True)
class GameComparison:
    app_id: str
    name: str
    home_price: StorePrice
    alternatives: tuple[ConvertedPrice, ...]
    is_fair: bool

    @property
    def cheapest_alternative(self) -> ConvertedPrice:
        return min(self.alternatives, key=lambda price: price.amount_in_home)

    @property
    def savings(self) -> float:
        return max(0.0, self.cheapest_alternative.amount_in_home - self.home_price.amount)

    @property
    def overpayment(self) -> float:
        return max(0.0, self.home_price.amount - self.cheapest_alternative.amount_in_home)


@dataclass(frozen=True)
class SkippedGame:
    app_id: str
    name: str
    reason: str
    category: SkipCategory
    region: str | None = None
    retryable: bool = False


class SkipCategory(str, Enum):
    NO_REGIONAL_PRICE = "no_regional_price"
    APP_UNAVAILABLE = "app_unavailable"
    TEMPORARY_FAILURE = "temporary_failure"
    INVALID_RESPONSE = "invalid_response"
    REGION_MISMATCH = "region_mismatch"
    REQUEST_FAILURE = "request_failure"

    @property
    def label(self) -> str:
        return {
            SkipCategory.NO_REGIONAL_PRICE: "No regional price",
            SkipCategory.APP_UNAVAILABLE: "App unavailable",
            SkipCategory.TEMPORARY_FAILURE: "Temporary request failures",
            SkipCategory.INVALID_RESPONSE: "Invalid Steam responses",
            SkipCategory.REGION_MISMATCH: "Region/currency mismatches",
            SkipCategory.REQUEST_FAILURE: "Permanent request failures",
        }[self]

    @property
    def is_technical_failure(self) -> bool:
        return self not in {
            SkipCategory.NO_REGIONAL_PRICE,
            SkipCategory.APP_UNAVAILABLE,
        }


@dataclass(frozen=True)
class AnalysisResult:
    comparisons: tuple[GameComparison, ...]
    skipped: tuple[SkippedGame, ...]
    exchange_rates: tuple[ExchangeRate, ...] = ()
    methodology: ComparisonMethodology | None = None

    @property
    def fair_games(self) -> tuple[GameComparison, ...]:
        return tuple(game for game in self.comparisons if game.is_fair)

    @property
    def expensive_games(self) -> tuple[GameComparison, ...]:
        return tuple(game for game in self.comparisons if not game.is_fair)

    @property
    def total_checked(self) -> int:
        return len(self.comparisons) + len(self.skipped)

    @property
    def technical_failures(self) -> tuple[SkippedGame, ...]:
        return tuple(
            game for game in self.skipped if game.category.is_technical_failure
        )

    @property
    def is_partial(self) -> bool:
        return bool(self.technical_failures)

    def skipped_count(self, category: SkipCategory) -> int:
        return sum(game.category is category for game in self.skipped)


@dataclass(frozen=True)
class ExchangeRate:
    currency: str
    rate_to_pln: float
    effective_date: str | None
    source: str = "NBP table A (mid)"
    cache_status: str = "live"

    def __post_init__(self) -> None:
        if isinstance(self.rate_to_pln, bool) or not isfinite(self.rate_to_pln) or self.rate_to_pln <= 0:
            raise ValueError("Exchange rate must be finite and positive")
        if self.effective_date is not None:
            if date.fromisoformat(self.effective_date).isoformat() != self.effective_date:
                raise ValueError("Effective date must use YYYY-MM-DD")


@dataclass(frozen=True)
class ComparisonMethodology:
    version: str = "1"
    rule: str = "FAIR means the PLN price is no higher than every selected converted price."
    limitations: tuple[str, ...] = (
        "Currency conversion is a price indicator, not a complete judgment of consumer fairness.",
        "Displayed US and EU prices may have different tax treatment; no VAT or sales-tax adjustment is applied.",
        "Payment-provider fees and conversion costs are excluded; NBP mid rates are not checkout quotes.",
        "Germany is the selected EUR storefront proxy; its prices do not represent every euro-area storefront.",
        "Regional prices may be cached or fetched at different times; publication dates can differ by currency.",
    )
