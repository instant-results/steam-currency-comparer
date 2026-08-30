"""Exchange-rate access independent from Steam and presentation code."""

from __future__ import annotations

from collections.abc import Iterable

from .http_client import JsonHttpClient


class ExchangeRateError(RuntimeError):
    """Raised when an exchange-rate response cannot be used."""


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
