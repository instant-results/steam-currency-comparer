import tempfile
import unittest
from pathlib import Path

from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.exchange_rates import CachedExchangeRateProvider
from steam_price_polisher.models import RegionalPriceResult, StorePrice
from steam_price_polisher.price_service import CachedPriceService
from steam_price_polisher.steam_access import SteamAccessError


class MutableClock:
    def __init__(self, value=1_000.0):
        self.value = value

    def __call__(self):
        return self.value


class FakePriceProvider:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.error = None

    def get_regional_price(self, app_id, region, expected_currency):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeRateProvider:
    def __init__(self, rates):
        self.rates = rates
        self.calls = 0

    def get_rates_to_pln(self, currencies):
        self.calls += 1
        return {currency: self.rates[currency] for currency in currencies}


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.clock = MutableClock()
        self.cache = SQLiteCache(
            Path(self.temp_directory.name) / "cache.sqlite3",
            clock=self.clock,
        )

    def test_price_is_loaded_from_cache_on_repeated_lookup(self):
        live_result = RegionalPriceResult(
            StorePrice("pl", "PLN", 49.99),
            "Test Game",
        )
        live = FakePriceProvider(live_result)
        service = CachedPriceService(live, self.cache, clock=self.clock)

        first = service.get_regional_price("10", "pl", "PLN")
        second = service.get_regional_price("10", "pl", "PLN")

        self.assertEqual(first.source, "live")
        self.assertEqual(second.source, "cache")
        self.assertEqual(second.result, live_result)
        self.assertEqual(live.calls, 1)

    def test_stale_price_is_used_when_refresh_fails(self):
        live_result = RegionalPriceResult(
            StorePrice("pl", "PLN", 49.99),
            "Test Game",
        )
        live = FakePriceProvider(live_result)
        service = CachedPriceService(
            live,
            self.cache,
            price_ttl=10,
            clock=self.clock,
        )
        service.get_regional_price("10", "pl", "PLN")
        self.clock.value += 11
        live.error = SteamAccessError("Steam unavailable")

        result = service.get_regional_price("10", "pl", "PLN")

        self.assertEqual(result.source, "stale cache")
        self.assertEqual(result.result, live_result)

    def test_exchange_rates_are_cached(self):
        upstream = FakeRateProvider({"USD": 3.75, "EUR": 4.25})
        provider = CachedExchangeRateProvider(
            upstream,
            self.cache,
            clock=self.clock,
        )

        first = provider.get_rates_to_pln(("USD", "EUR"))
        second = provider.get_rates_to_pln(("USD", "EUR"))

        self.assertEqual(first, second)
        self.assertEqual(upstream.calls, 1)


if __name__ == "__main__":
    unittest.main()
