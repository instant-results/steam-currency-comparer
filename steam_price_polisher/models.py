"""Shared data structures used across the application layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WishlistItem:
    app_id: str
    name: str | None = None


@dataclass(frozen=True)
class WishlistResult:
    items: tuple[WishlistItem, ...]
    source: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StorePrice:
    region: str
    currency: str
    amount: float


@dataclass(frozen=True)
class RegionalPriceResult:
    price: StorePrice | None
    game_name: str | None


@dataclass(frozen=True)
class ConvertedPrice:
    region: str
    currency: str
    original_amount: float
    rate_to_home: float
    amount_in_home: float


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


@dataclass(frozen=True)
class AnalysisResult:
    comparisons: tuple[GameComparison, ...]
    skipped: tuple[SkippedGame, ...]

    @property
    def fair_games(self) -> tuple[GameComparison, ...]:
        return tuple(game for game in self.comparisons if game.is_fair)

    @property
    def expensive_games(self) -> tuple[GameComparison, ...]:
        return tuple(game for game in self.comparisons if not game.is_fair)

    @property
    def total_checked(self) -> int:
        return len(self.comparisons) + len(self.skipped)
