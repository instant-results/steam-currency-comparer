from dataclasses import replace
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.exchange_rates import CachedExchangeRateProvider
from steam_price_polisher.models import ExchangeRate, PriceStatus, RegionalPriceResult, StorePrice
from steam_price_polisher.price_service import CachedPriceService
from steam_price_polisher.steam_access import SteamProtocolError, SteamTemporaryError


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

    def get_rate_details(self, currencies):
        self.calls += 1
        return {currency: ExchangeRate(currency, self.rates[currency], "2026-09-08") for currency in currencies}


class CacheTests(unittest.TestCase):
    def test_catalog_credits_refresh_old_cache_and_survive_reopen(self):
        old = RegionalPriceResult.available(StorePrice("pl", "PLN", 10, 10, 0), "Game")
        self.cache.put_price("10", "pl", "PLN", old)
        live = FakePriceProvider(replace(old, developers=("Studio",), publishers=("Publisher", "Co-publisher")))
        service = CachedPriceService(live, self.cache, clock=self.clock, require_credits=True)
        self.assertEqual(service.get_regional_price("10", "pl", "PLN").source, "live")
        reopened = SQLiteCache(Path(self.temp_directory.name) / "cache.sqlite3", clock=self.clock)
        service = CachedPriceService(live, reopened, clock=self.clock, require_credits=True)
        result = service.get_regional_price("10", "pl", "PLN")
        self.assertEqual(result.source, "cache")
        self.assertEqual(result.result.publishers, ("Publisher", "Co-publisher"))
        self.assertEqual(result.result.developers, ("Studio",))
        self.assertEqual(live.calls, 1)


    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.clock = MutableClock()
        self.cache = SQLiteCache(
            Path(self.temp_directory.name) / "cache.sqlite3",
            clock=self.clock,
        )

    def test_old_missing_price_is_rechecked_and_free_flag_survives_reopen(self):
        self.cache.put_price("10", "pl", "PLN", RegionalPriceResult.no_regional_price("Demo"))
        free = RegionalPriceResult.no_regional_price("Demo", is_free=True)
        live = FakePriceProvider(free)
        service = CachedPriceService(live, self.cache, clock=self.clock, require_sale_metadata=True)
        self.assertEqual(service.get_regional_price("10", "pl", "PLN").source, "live")
        reopened = SQLiteCache(Path(self.temp_directory.name) / "cache.sqlite3", clock=self.clock)
        service = CachedPriceService(live, reopened, clock=self.clock, require_sale_metadata=True)
        lookup = service.get_regional_price("10", "pl", "PLN")
        self.assertEqual(lookup.source, "cache")
        self.assertTrue(lookup.result.is_free)
        self.assertEqual(live.calls, 1)

    def test_connection_scope_reuses_connection_and_commits_each_operation(self):
        result = RegionalPriceResult.available(StorePrice("pl", "PLN", 10), "Game")
        observer = SQLiteCache(Path(self.temp_directory.name) / "cache.sqlite3")
        with patch.object(self.cache, "_connect", wraps=self.cache._connect) as connect:
            with self.cache.connection_scope():
                self.cache.put_price("10", "pl", "PLN", result)
                with self.cache._connection() as connection:
                    self.assertFalse(connection.in_transaction)
                with self.cache.connection_scope():
                    self.assertEqual(self.cache.get_price("10", "pl", "PLN").result, result)
                self.cache.put_observation("offer", "10", "pl", {"status": "unavailable"})
                self.assertEqual(observer.get_price("10", "pl", "PLN").result, result)
                self.assertIsNotNone(observer.get_observation("offer", "10", "pl"))
                self.assertEqual(connect.call_count, 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")
            self.assertIsNotNone(self.cache.get_price("10", "pl", "PLN"))
            self.assertEqual(connect.call_count, 2)

    def test_connection_scope_closes_after_exception_and_can_be_reopened(self):
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            with self.cache.connection_scope():
                self.cache.put_exchange_rate("USD", 4)
                with self.cache._connection() as connection:
                    pass
                raise RuntimeError("interrupted")
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        with self.cache.connection_scope():
            self.assertEqual(self.cache.get_exchange_rate("USD").rate, 4)
            self.cache.put_exchange_rate("EUR", 5)
        self.assertEqual(self.cache.get_exchange_rate("EUR").rate, 5)

    def test_failed_scoped_write_preserves_prior_commit_and_allows_retry(self):
        with self.cache._connection() as connection:
            connection.execute("""CREATE TRIGGER reject_observation BEFORE INSERT ON batch_observations
                WHEN NEW.app_id = '20' BEGIN SELECT RAISE(ABORT, 'rejected'); END""")
        with self.cache.connection_scope():
            self.cache.put_observation("metadata", "10", "pl", {"name": "Saved"})
            with self.assertRaises(sqlite3.IntegrityError):
                self.cache.put_observation("metadata", "20", "pl", {"name": "Rejected"})
            self.assertIsNone(self.cache.get_observation("metadata", "20", "pl"))
            self.cache.put_observation("metadata", "30", "pl", {"name": "Next"})
            observer = SQLiteCache(Path(self.temp_directory.name) / "cache.sqlite3")
            self.assertEqual(observer.get_observation("metadata", "10", "pl")[0], {"name": "Saved"})
            self.assertEqual(observer.get_observation("metadata", "30", "pl")[0], {"name": "Next"})

    def test_connection_scopes_are_isolated_between_threads(self):
        def other_thread():
            with self.cache.connection_scope():
                self.assertEqual(self.cache.get_exchange_rate("USD").rate, 4)
                self.cache.put_exchange_rate("EUR", 5)
                with self.cache._connection() as connection:
                    pass
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")
            return connection

        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.cache.connection_scope():
                self.cache.put_exchange_rate("USD", 4)
                with self.cache._connection() as connection:
                    pass
                other = pool.submit(other_thread).result(timeout=5)
                self.assertIsNot(other, connection)
                self.assertEqual(self.cache.get_exchange_rate("EUR").rate, 5)
                self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_price_is_loaded_from_cache_on_repeated_lookup(self):
        live_result = RegionalPriceResult.available(
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
        live_result = RegionalPriceResult.available(
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
        live.error = SteamTemporaryError(
            "Steam unavailable",
            app_id="10",
            region="pl",
        )

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

    def test_stale_price_does_not_hide_a_protocol_failure(self):
        live_result = RegionalPriceResult.available(
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
        live.error = SteamProtocolError(
            "Malformed response",
            app_id="10",
            region="pl",
        )

        with self.assertRaises(SteamProtocolError):
            service.get_regional_price("10", "pl", "PLN")

    def test_legacy_missing_status_is_migrated_without_losing_data(self):
        legacy_path = Path(self.temp_directory.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE regional_prices (
                        app_id TEXT NOT NULL,
                        region TEXT NOT NULL,
                        currency TEXT NOT NULL,
                        amount REAL,
                        game_name TEXT,
                        status TEXT NOT NULL CHECK(
                            status IN ('available', 'missing')
                        ),
                        fetched_at REAL NOT NULL,
                        PRIMARY KEY (app_id, region)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO regional_prices (
                        app_id, region, currency, amount, game_name, status, fetched_at
                    ) VALUES ('10', 'pl', 'PLN', NULL, 'Legacy Game', 'missing', 900)
                    """
                )

        migrated = SQLiteCache(legacy_path, clock=self.clock)
        entry = migrated.get_price("10", "pl", "PLN")

        self.assertIsNotNone(entry)
        self.assertEqual(entry.result.status, PriceStatus.NO_REGIONAL_PRICE)
        self.assertEqual(entry.result.game_name, "Legacy Game")


if __name__ == "__main__":
    unittest.main()
