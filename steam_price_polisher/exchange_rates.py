"""NBP rates with publication dates and explicit cache provenance."""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Protocol

from .cache import SQLiteCache
from .http_client import JsonHttpClient, is_network_access_denied
from .models import ExchangeRate
from .event_log import emit


class ExchangeRateError(RuntimeError):
    """Raised when exchange rates cannot be obtained or validated."""


class ExchangeRateProvider(Protocol):
    def get_rate_details(self, currencies: Iterable[str]) -> dict[str, ExchangeRate]: ...


class NbpExchangeRateProvider:
    def __init__(self, http_client: JsonHttpClient) -> None:
        self._http_client = http_client

    def get_rates_to_pln(self, currencies: Iterable[str]) -> dict[str, float]:
        return {key: rate.rate_to_pln for key, rate in self.get_rate_details(currencies).items()}

    def get_rate_details(self, currencies: Iterable[str]) -> dict[str, ExchangeRate]:
        rates = {}
        for currency in dict.fromkeys(value.upper() for value in currencies):
            if currency == "PLN":
                rates[currency] = ExchangeRate("PLN", 1.0, None, "Identity conversion", "identity")
                continue
            url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.lower()}/?format=json"
            try:
                payload = self._http_client.get_json(url)
            except Exception as exc:
                raise ExchangeRateError(f"Could not fetch the {currency} exchange rate: {exc}") from exc
            try:
                if payload["code"] != currency or payload["table"] != "A":
                    raise ValueError("Unexpected currency or table")
                rows = payload["rates"]
                if not isinstance(rows, list) or len(rows) != 1:
                    raise ValueError("Expected one current rate")
                row = rows[0]
                if isinstance(row["mid"], bool) or not isinstance(row["mid"], (int, float)):
                    raise ValueError("Invalid numeric rate")
                if not isinstance(row["effectiveDate"], str):
                    raise ValueError("Missing publication date")
                rates[currency] = ExchangeRate(currency, float(row["mid"]), row["effectiveDate"])
            except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
                raise ExchangeRateError(f"NBP returned an invalid {currency} exchange-rate response") from exc
        return rates


class CachedExchangeRateProvider:
    def __init__(self, upstream: ExchangeRateProvider, cache: SQLiteCache, *,
                 ttl: float = 24 * 60 * 60, clock: Callable[[], float] = time.time) -> None:
        self._upstream = upstream
        self._cache = cache
        self._ttl = ttl
        self._clock = clock

    def get_rates_to_pln(self, currencies: Iterable[str]) -> dict[str, float]:
        return {key: rate.rate_to_pln for key, rate in self.get_rate_details(currencies).items()}

    def get_rate_details(self, currencies: Iterable[str]) -> dict[str, ExchangeRate]:
        requested = tuple(dict.fromkeys(currency.upper() for currency in currencies))
        rates = {}
        fallback = {}
        missing = []
        for currency in requested:
            if currency == "PLN":
                rates[currency] = ExchangeRate("PLN", 1.0, None, "Identity conversion", "identity")
                continue
            cached = self._cache.get_exchange_rate(currency)
            if cached is not None:
                try:
                    detail = ExchangeRate(currency, cached.rate, cached.effective_date, cache_status="cache")
                except (ValueError, TypeError):
                    cached = None
            if cached is None:
                missing.append(currency)
            elif self._clock() - cached.fetched_at <= self._ttl and cached.effective_date is not None:
                rates[currency] = detail
            else:
                fallback[currency] = replace(detail, cache_status="stale cache")
                missing.append(currency)
        if missing:
            try:
                fetched = self._upstream.get_rate_details(missing)
            except ExchangeRateError as exc:
                if is_network_access_denied(exc):
                    raise
                if not all(currency in fallback for currency in missing):
                    raise
                fetched = {currency: fallback[currency] for currency in missing}
            else:
                for currency, rate in fetched.items():
                    self._cache.put_exchange_rate(currency, rate.rate_to_pln, rate.effective_date)
            rates.update(fetched)
        for currency in requested:
            emit("cache_access", cache_kind="exchange_rate", source=rates[currency].cache_status)
        return {currency: rates[currency] for currency in requested}
