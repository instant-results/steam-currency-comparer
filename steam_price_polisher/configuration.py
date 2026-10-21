"""Validated storefront selections for command-line and future UI clients."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType

# One representative country per live Steam currency; regional USD groups are excluded.
STOREFRONTS = MappingProxyType(json.loads(Path(__file__).with_name("storefronts.json").read_text(encoding="utf-8")))
REGION_CURRENCIES = MappingProxyType({region: value["currency"] for region, value in STOREFRONTS.items()})
MAX_COMPARISONS = len(REGION_CURRENCIES) - 1


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
            raise ValueError(f"Unsupported region: {region!r}. Choose a supported Steam storefront.")
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
        alternatives = tuple(self.alternatives)
        if not 1 <= len(alternatives) <= MAX_COMPARISONS:
            raise ValueError(f"Choose between one and {MAX_COMPARISONS} comparison regions")
        seen = {self.home.region}
        for alternative in alternatives:
            if not isinstance(alternative, RegionConfig):
                raise ValueError("Alternatives must contain RegionConfig values")
            if alternative.region in seen:
                raise ValueError("Comparison regions must be unique and exclude the home region")
            seen.add(alternative.region)
        object.__setattr__(self, "alternatives", alternatives)

    @classmethod
    def from_regions(cls, regions: Iterable[str], home: str = "pl") -> ComparisonConfig:
        if isinstance(regions, str):
            raise ValueError("Supply a sequence of region codes, not a single string")
        return cls(home=RegionConfig.from_region(home), alternatives=tuple(RegionConfig.from_region(region) for region in regions))

    @property
    def currencies(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(region.currency for region in self.alternatives))
