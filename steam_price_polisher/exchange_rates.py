"""Exchange-rate access independent from Steam and presentation code."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Protocol

from .cache import SQLiteCache
from .http_client import JsonHttpClient


class ExchangeRateError(RuntimeError):
    """Raised when an exchange-rate response cannot be used."""


class ExchangeRateProvider(Protocol):
    def get_rates_to_pln(self, currencies: Iterable[str]) -> dict[str, float]:
        """Return PLN conversion rates for the requested currencies."""


class NbpExchangeRateProvider:
    def __init__(self, http_client: JsonHttpClient) -> None:
        self._http_client = http_client

    def get_rates_to_pln(self, currencies: Iterable[str]) -> dict[str, float]:
        rates: dict[str, float] = {}
        for requested_currency in currencies:
            currency = requested_currency.upper()
            if currency == "PLN":
                rates[currency] = 1.0
                continue

            url = (
                "https://api.nbp.pl/api/exchangerates/rates/a/"
                f"{currency.lower()}/?format=json"
            )
            try:
                payload = self._http_client.get_json(url)
                rate = float(payload["rates"][0]["mid"])
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ExchangeRateError(
                    f"NBP returned an invalid {currency} exchange-rate response"
                ) from exc
            except Exception as exc:
                raise ExchangeRateError(
                    f"Could not fetch the {currency} exchange rate: {exc}"
                ) from exc

            if rate <= 0:
                raise ExchangeRateError(
                    f"NBP returned a non-positive {currency} exchange rate"
                )
            rates[currency] = rate
        return rates


class CachedExchangeRateProvider:
    def __init__(
        self,
        upstream: ExchangeRateProvider,
        cache: SQLiteCache,
        *,
        ttl: float = 24 * 60 * 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._upstream = upstream
        self._cache = cache
        self._ttl = ttl
        self._clock = clock

    def get_rates_to_pln(self, currencies: Iterable[str]) -> dict[str, float]:
        requested = tuple(dict.fromkeys(currency.upper() for currency in currencies))
        rates: dict[str, float] = {}
        stale_rates: dict[str, float] = {}
        missing: list[str] = []

        for currency in requested:
            if currency == "PLN":
                rates[currency] = 1.0
                continue
            cached = self._cache.get_exchange_rate(currency)
            if cached is None:
                missing.append(currency)
            elif self._clock() - cached.fetched_at <= self._ttl:
                rates[currency] = cached.rate
            else:
                stale_rates[currency] = cached.rate
                missing.append(currency)

        if missing:
            try:
                fetched = self._upstream.get_rates_to_pln(missing)
            except ExchangeRateError:
                if not all(currency in stale_rates for currency in missing):
                    raise
                fetched = {currency: stale_rates[currency] for currency in missing}
            else:
                for currency, rate in fetched.items():
                    self._cache.put_exchange_rate(currency, rate)
            rates.update(fetched)

        return {currency: rates[currency] for currency in requested}
