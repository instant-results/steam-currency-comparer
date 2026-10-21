import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.exchange_rates import CachedExchangeRateProvider, ExchangeRateError, NbpExchangeRateProvider
from steam_price_polisher.http_client import HttpClientError, is_network_access_denied
from steam_price_polisher.models import ExchangeRate
from steam_price_polisher.web_app import JobManager, rates_to_baseline
from tests.test_exchange_rates import FakeHttpClient, table_payload


class NbpTableCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "cache.sqlite3"
        self.now = 1000
        self.cache = SQLiteCache(self.path, clock=lambda: self.now)
        self.http = FakeHttpClient({
            "A": table_payload(USD=4, EUR=4.4, NOK=0.4, GBP=5, JPY=0.025),
            "B": table_payload("B", "2026-10-14", AED=1.1, VND=0.00015),
        })
        self.provider = self.make_provider()

    def make_provider(self):
        return CachedExchangeRateProvider(NbpExchangeRateProvider(self.http), self.cache,
                                          ttl=100, clock=lambda: self.now)

    def test_initial_selection_caches_unselected_rates_across_reopen(self):
        first = self.provider.get_rate_details(["USD", "EUR", "PLN"])
        self.assertEqual(list(first), ["USD", "EUR", "PLN"])
        self.assertEqual(len(self.http.urls), 2)
        self.cache = SQLiteCache(self.path, clock=lambda: self.now)
        self.now += 1
        later = self.make_provider().get_rate_details(["GBP", "NOK", "PLN"])
        self.assertEqual(len(self.http.urls), 2)
        self.assertEqual(later["GBP"].cache_status, "cache")
        self.assertEqual(self.cache.get_exchange_rate("GBP").fetched_at, 1000)
        self.assertEqual(later["PLN"].cache_status, "identity")
        self.assertEqual(rates_to_baseline(later, "GBP"), {"GBP": 1, "NOK": 0.08, "PLN": 0.2})

    def test_table_b_is_preloaded_and_its_rates_are_reused(self):
        self.provider.get_rate_details(["USD"])
        self.assertEqual(len(self.http.urls), 2)
        self.assertEqual(self.cache.get_exchange_rate("AED").fetched_at, 1000)
        self.now += 1
        details = self.make_provider().get_rate_details(["AED", "USD"])
        self.assertEqual(details["AED"].cache_status, "cache")
        self.assertEqual(len(self.http.urls), 2)
        self.assertIn("/tables/b/", self.http.urls[-1])
        self.assertEqual(details["AED"].effective_date, "2026-10-14")
        self.assertEqual(details["AED"].source, "NBP table B (mid)")
        self.assertEqual(details["USD"].effective_date, "2026-10-20")
        self.cache = SQLiteCache(self.path, clock=lambda: self.now)
        warm = self.make_provider().get_rate_details(["VND"])["VND"]
        self.assertEqual(warm.rate_to_pln, 0.00015)
        self.assertEqual(warm.source, "NBP table B (mid)")
        self.assertEqual(warm.cache_status, "cache")
        self.assertEqual(len(self.http.urls), 2)

    def test_api_mid_values_are_not_scaled_as_printed_hundred_unit_quotes(self):
        details = self.provider.get_rates_to_pln(["JPY", "VND"])
        self.assertEqual(details, {"JPY": 0.025, "VND": 0.00015})

    def test_table_b_outage_is_not_a_dependency_for_table_a(self):
        self.http.responses["B"] = HttpClientError("offline")
        details = self.provider.get_rate_details(["GBP", "NOK"])
        self.assertEqual(set(details), {"GBP", "NOK"})
        self.assertEqual(len(self.http.urls), 2)

    def test_table_a_outage_does_not_block_table_b_only_selection(self):
        self.http.responses["A"] = HttpClientError("offline")
        details = self.provider.get_rate_details(["AED", "VND"])
        self.assertEqual(details["AED"].cache_status, "live")
        self.assertEqual(details["VND"].source, "NBP table B (mid)")
        self.assertEqual(len(self.http.urls), 2)
        self.assertIsNone(self.cache.get_exchange_rate_table_fetched_at("A"))
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("B"), 1000)

    def test_each_table_refreshes_independently_even_when_requested_rates_are_fresh(self):
        self.provider.get_rate_details(["USD"])
        self.now = 1050
        self.cache.put_exchange_rate_table("A", {"USD": ExchangeRate("USD", 4.1, "2026-10-21")})
        self.now = 1101
        details = self.make_provider().get_rate_details(["USD"])
        self.assertEqual(details["USD"].cache_status, "cache")
        self.assertEqual(details["USD"].rate_to_pln, 4.1)
        self.assertEqual(len(self.http.urls), 3)
        self.assertIn("/tables/b/", self.http.urls[-1])
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("A"), 1050)
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("B"), 1101)
        self.now = 1151
        details = self.make_provider().get_rate_details(["VND"])
        self.assertEqual(details["VND"].cache_status, "cache")
        self.assertEqual(len(self.http.urls), 4)
        self.assertIn("/tables/a/", self.http.urls[-1])
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("B"), 1101)

    def test_empty_and_identity_only_requests_do_not_preload_tables(self):
        self.assertEqual(self.provider.get_rate_details([]), {})
        self.assertEqual(self.provider.get_rates_to_pln(["PLN"]), {"PLN": 1})
        self.assertEqual(self.http.urls, [])

    def test_successful_table_survives_failure_of_other_required_table(self):
        self.http.responses["B"] = HttpClientError("offline")
        with self.assertRaises(ExchangeRateError):
            self.provider.get_rate_details(["USD", "AED"])
        self.assertEqual(self.cache.get_exchange_rate("GBP").rate, 5)
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("A"), self.now)
        self.assertIsNone(self.cache.get_exchange_rate_table_fetched_at("B"))
        self.assertEqual(self.make_provider().get_rate_details(["EUR"])["EUR"].cache_status, "cache")
        self.assertEqual(len(self.http.urls), 3)
        self.assertIn("/tables/b/", self.http.urls[-1])

    def test_expired_table_refreshes_all_rates_with_one_timestamp(self):
        self.provider.get_rate_details(["USD"])
        self.now += 101
        self.http.responses["A"] = table_payload("A", "2026-10-21", USD=4.1, GBP=5.1)
        details = self.make_provider().get_rate_details(["GBP", "USD"])
        self.assertEqual(len(self.http.urls), 4)
        for code in ("GBP", "USD"):
            self.assertEqual(details[code].cache_status, "live")
            self.assertEqual(self.cache.get_exchange_rate(code).fetched_at, self.now)
            self.assertEqual(details[code].effective_date, "2026-10-21")

    def test_mixed_legacy_and_live_rates_match_retrieval_timestamps(self):
        self.cache.put_exchange_rate("USD", 3.9, "2026-10-19")
        self.now += 1
        details = self.provider.get_rate_details(["USD", "EUR"])
        self.assertEqual(details["USD"].rate_to_pln, 4)
        self.assertEqual(details["USD"].cache_status, "live")
        self.assertEqual(self.cache.get_exchange_rate("USD").fetched_at, self.now)

    def test_stale_fallback_preserves_table_source_and_original_age(self):
        self.provider.get_rate_details(["AED"])
        self.now += 101
        self.http.responses["B"] = HttpClientError("offline")
        details = self.provider.get_rate_details(["USD", "AED"])
        self.assertEqual(details["USD"].cache_status, "live")
        self.assertEqual(details["AED"].cache_status, "stale cache")
        self.assertEqual(details["AED"].source, "NBP table B (mid)")
        self.assertEqual(details["AED"].effective_date, "2026-10-14")
        self.assertEqual(self.cache.get_exchange_rate("AED").fetched_at, 1000)
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("B"), 1000)

    def test_table_a_failure_can_use_stale_a_and_live_b(self):
        self.provider.get_rate_details(["USD"])
        self.now += 101
        self.http.responses["A"] = HttpClientError("offline")
        details = self.provider.get_rate_details(["USD", "AED"])
        self.assertEqual(details["USD"].cache_status, "stale cache")
        self.assertEqual(details["AED"].cache_status, "live")

    def test_network_denial_never_uses_stale_data_or_attempts_next_table(self):
        self.provider.get_rate_details(["USD"])
        self.now += 101
        self.http.responses["A"] = HttpClientError("private information", network_access_denied=True)
        with self.assertRaises(ExchangeRateError) as caught:
            self.provider.get_rate_details(["USD", "AED"])
        self.assertTrue(is_network_access_denied(caught.exception))
        self.assertNotIn("private information", str(caught.exception))
        self.assertEqual(len(self.http.urls), 3)

    def test_unpublished_currency_does_not_redownload_fresh_tables(self):
        for _ in range(2):
            with self.assertRaisesRegex(ExchangeRateError, "do not provide: XYZ"):
                self.make_provider().get_rate_details(["XYZ"])
        self.assertEqual(len(self.http.urls), 2)

    def test_malformed_table_cannot_partially_overwrite_cache(self):
        self.provider.get_rate_details(["USD"])
        self.now += 101
        self.http.responses["A"] = table_payload(USD=9, EUR=float("nan"))
        details = self.provider.get_rate_details(["USD"])
        self.assertEqual(details["USD"].rate_to_pln, 4)
        self.assertEqual(details["USD"].cache_status, "stale cache")
        self.assertEqual(self.cache.get_exchange_rate_table_fetched_at("A"), 1000)
        self.assertEqual(self.cache.get_exchange_rate("USD").fetched_at, 1000)

    def test_bulk_cache_write_rolls_back_rates_and_marker_together(self):
        self.cache.put_exchange_rate("USD", 3.9, "2026-10-19")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""CREATE TRIGGER reject_eur BEFORE INSERT ON exchange_rates
                WHEN NEW.currency = 'EUR' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.cache.put_exchange_rate_table("A", {
                "USD": ExchangeRate("USD", 4, "2026-10-20"),
                "EUR": ExchangeRate("EUR", 4.4, "2026-10-20"),
            })
        self.assertEqual(self.cache.get_exchange_rate("USD").rate, 3.9)
        self.assertIsNone(self.cache.get_exchange_rate("EUR"))
        self.assertIsNone(self.cache.get_exchange_rate_table_fetched_at("A"))

    def test_schema_eight_rate_migration_keeps_publication_and_retrieval_dates(self):
        legacy = Path(self.temp.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as connection, connection:
            connection.execute("""CREATE TABLE exchange_rates (
                currency TEXT PRIMARY KEY, rate_to_pln REAL NOT NULL,
                fetched_at REAL NOT NULL, effective_date TEXT)""")
            connection.execute("INSERT INTO exchange_rates VALUES ('USD', 4, 1000, '2026-10-20')")
            connection.execute("PRAGMA user_version = 8")
        self.cache = SQLiteCache(legacy, clock=lambda: self.now)
        row = self.cache.get_exchange_rate("USD")
        self.assertEqual((row.rate, row.fetched_at, row.effective_date, row.source),
                         (4, 1000, "2026-10-20", "NBP table A (mid)"))
        self.assertIsNone(self.cache.get_exchange_rate_table_fetched_at("A"))
        self.assertEqual(self.make_provider().get_rate_details(["USD"])["USD"].cache_status, "live")
        self.assertEqual(len(self.http.urls), 2)
        with closing(sqlite3.connect(legacy)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 9)

    def test_web_jobs_only_expose_selected_rates_but_reuse_other_table_rates(self):
        manager = JobManager(self.temp.name, start_worker=False)
        with patch("steam_price_polisher.web_app.UrllibJsonHttpClient", return_value=self.http), patch(
            "steam_price_polisher.web_app.AnalysisRunner"
        ) as runner:
            runner.return_value.run.side_effect = [iter(()), iter(())]
            first = manager.submit("example", ComparisonConfig(), "first")
            manager.execute(first)
            second = manager.submit("example", ComparisonConfig.from_regions(["no"], home="gb"), "second")
            manager.execute(second)
        self.assertEqual(first.snapshot()["state"], "complete")
        self.assertEqual(second.snapshot()["state"], "complete")
        self.assertEqual(len(self.http.urls), 2)
        rows = {row["currency"]: row for row in second.snapshot()["rates"]}
        self.assertEqual(set(rows), {"NOK", "GBP"})
        self.assertEqual(rows["GBP"]["source"], "NBP table A (mid)")
        self.assertEqual(rows["GBP"]["cache_status"], "cache")
        self.assertIsNotNone(rows["GBP"]["retrieved_at_utc"])
        self.assertIsNotNone(rows["GBP"]["checked_at_utc"])


if __name__ == "__main__":
    unittest.main()
