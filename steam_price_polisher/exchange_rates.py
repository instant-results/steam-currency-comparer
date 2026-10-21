"""NBP rates with publication dates and explicit cache provenance."""
from __future__ import annotations

import re
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


def requested_currencies(currencies: Iterable[str]) -> tuple[str, ...]:
    if isinstance(currencies, str):
        raise ValueError("Supply a collection of currency codes")
    values = tuple(currencies)
    if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{3}", value) for value in values):
        raise ValueError("Currency codes must contain three ASCII letters")
    return tuple(dict.fromkeys(value.upper() for value in values))


def identity_rate() -> ExchangeRate:
    return ExchangeRate("PLN", 1.0, None, "Identity conversion", "identity")


class NbpExchangeRateProvider:
    def __init__(self, http_client: JsonHttpClient) -> None:
        self._http_client = http_client

    def get_rates_to_pln(self, currencies: Iterable[str]) -> dict[str, float]:
        return {key: rate.rate_to_pln for key, rate in self.get_rate_details(currencies).items()}

    def get_rate_details(self, currencies: Iterable[str]) -> dict[str, ExchangeRate]:
        requested = requested_currencies(currencies)
        rates = {"PLN": identity_rate()}
        errors = []
        if any(currency != "PLN" for currency in requested):
            for table in ("A", "B"):
                try:
                    rates.update(self.get_rate_table(table))
                except ExchangeRateError as exc:
                    if is_network_access_denied(exc):
                        raise
                    errors.append(exc)
        missing = [currency for currency in requested if currency not in rates]
        if missing:
            if errors:
                raise ExchangeRateError(f"Could not obtain exchange rates for: {', '.join(missing)}") from errors[0]
            raise ExchangeRateError(f"NBP tables A and B do not provide: {', '.join(missing)}")
        return {currency: rates[currency] for currency in requested}

    def get_rate_table(self, table: str) -> dict[str, ExchangeRate]:
        """Read one complete latest table; API mid values are PLN per currency unit."""
        if table not in {"A", "B"}:
            raise ValueError("Choose NBP table A or B")
        url = f"https://api.nbp.pl/api/exchangerates/tables/{table.lower()}/?format=json"
        try:
            payload = self._http_client.get_json(url)
        except Exception as exc:
            raise ExchangeRateError(f"Could not fetch NBP table {table}") from exc
        try:
            if not isinstance(payload, list) or len(payload) != 1:
                raise ValueError("Expected one current table")
            snapshot = payload[0]
            if snapshot["table"] != table or not isinstance(snapshot["effectiveDate"], str):
                raise ValueError("Unexpected table or publication date")
            rows = snapshot["rates"]
            if not isinstance(rows, list) or not rows:
                raise ValueError("Expected a nonempty rate list")
            rates = {}
            for row in rows:
                code, value = row["code"], row["mid"]
                if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code) or code == "PLN" or code in rates:
                    raise ValueError("Invalid or duplicate currency")
                if type(value) not in {int, float}:
                    raise ValueError("Invalid numeric rate")
                rates[code] = ExchangeRate(code, float(value), snapshot["effectiveDate"],
                                           source=f"NBP table {table} (mid)")
            return rates
        except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
            raise ExchangeRateError(f"NBP returned an invalid table {table} response") from exc


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
        requested = requested_currencies(currencies)
        rates = {}
        fallback = {}
        missing = []
        for currency in requested:
            if currency == "PLN":
                rates[currency] = identity_rate()
                continue
            cached = self._cache.get_exchange_rate(currency)
            if cached is not None:
                try:
                    detail = ExchangeRate(currency, cached.rate, cached.effective_date,
                                          source=cached.source, cache_status="cache")
                except (ValueError, TypeError):
                    cached = None
            if cached is None:
                missing.append(currency)
            elif self._clock() - cached.fetched_at <= self._ttl and cached.effective_date is not None:
                rates[currency] = detail
            else:
                fallback[currency] = replace(detail, cache_status="stale cache")
                missing.append(currency)
        # Explicitly declared table providers can cache all observations. Providers
        # implementing only get_rate_details keep the existing per-currency contract.
        if any(currency != "PLN" for currency in requested) and callable(getattr(type(self._upstream), "get_rate_table", None)):
            self._refresh_tables(missing, rates, fallback)
        elif missing:
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
                    self._cache.put_exchange_rate(currency, rate.rate_to_pln, rate.effective_date, source=rate.source)
            rates.update(fetched)
        for currency in requested:
            emit("cache_access", cache_kind="exchange_rate", source=rates[currency].cache_status)
        return {currency: rates[currency] for currency in requested}

    def _refresh_tables(self, missing, rates, fallback):
        errors = {}
        unresolved = set(missing)
        for table in ("A", "B"):
            fetched_at = self._cache.get_exchange_rate_table_fetched_at(table)
            if fetched_at is not None and self._clock() - fetched_at <= self._ttl:
                # Tables have independent ages; reuse each fresh snapshot.
                continue
            try:
                fetched = self._upstream.get_rate_table(table)
            except ExchangeRateError as exc:
                if is_network_access_denied(exc):
                    raise
                errors[table] = exc
            else:
                self._cache.put_exchange_rate_table(table, fetched)
                # Refresh already-selected rates from this table too, so returned
                # values match the cache's retrieval timestamps used by the web API.
                rates.update(fetched)
                unresolved.difference_update(fetched)
        for currency in missing:
            if currency not in unresolved:
                continue
            old = fallback.get(currency)
            if old is not None and any(old.source == f"NBP table {table} (mid)" for table in errors):
                rates[currency] = old
            elif errors:
                raise ExchangeRateError(f"Could not obtain the {currency} exchange rate") from next(iter(errors.values()))
            else:
                raise ExchangeRateError(f"NBP tables A and B do not provide: {currency}")
