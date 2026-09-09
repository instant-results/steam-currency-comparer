"""Validated storefront selections for command-line and future UI clients."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType

# Limited to the existing supported Steam storefront/currency pairs.
REGION_CURRENCIES = MappingProxyType({"pl": "PLN", "us": "USD", "de": "EUR"})


@dataclass(frozen=True)
class RegionConfig:
    region: str
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.region, str) or not isinstance(self.currency, str):
            raise ValueError("Region and currency must be strings")
        region = self.region.strip().lower()
        currency = self.currency.strip().upper()
        if region not in REGION_CURRENCIES:
            raise ValueError(f"Unsupported region: {region!r}. Choose pl, us, or de.")
        expected = REGION_CURRENCIES[region]
        if currency != expected:
            raise ValueError(f"Region {region} requires {expected}, not {currency!r}")
        object.__setattr__(self, "region", region)
        object.__setattr__(self, "currency", currency)

    @classmethod
    def from_region(cls, region: str) -> RegionConfig:
        if not isinstance(region, str):
            raise ValueError("Region must be a string")
        normalized = region.strip().lower()
        return cls(normalized, REGION_CURRENCIES.get(normalized, ""))


@dataclass(frozen=True)
class ComparisonConfig:
    home: RegionConfig = RegionConfig("pl", "PLN")
    alternatives: tuple[RegionConfig, ...] = (
        RegionConfig("us", "USD"), RegionConfig("de", "EUR"),
    )

    def __post_init__(self) -> None:
        if not isinstance(self.home, RegionConfig):
            raise ValueError("Home must be a RegionConfig")
        if self.home.region != "pl":
            raise ValueError("Only Poland (PLN) is supported as the home storefront")
        alternatives = tuple(self.alternatives)
        if not alternatives:
            raise ValueError("At least one comparison region is required")
        seen = {self.home.region}
        for alternative in alternatives:
            if not isinstance(alternative, RegionConfig):
                raise ValueError("Alternatives must contain RegionConfig values")
            if alternative.region in seen:
                raise ValueError("Comparison regions must be unique and exclude the home region")
            seen.add(alternative.region)
        object.__setattr__(self, "alternatives", alternatives)

    @classmethod
    def from_regions(cls, regions: Iterable[str]) -> ComparisonConfig:
        if isinstance(regions, str):
            raise ValueError("Supply a sequence of region codes, not a single string")
        return cls(alternatives=tuple(RegionConfig.from_region(region) for region in regions))

    @property
    def currencies(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(region.currency for region in self.alternatives))
