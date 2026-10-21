import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.exchange_rates import CachedExchangeRateProvider, ExchangeRateError, NbpExchangeRateProvider
from steam_price_polisher.models import AnalysisResult, ComparisonMethodology, ExchangeRate
from steam_price_polisher.presentation import ConsolePresenter
from tests.test_exchange_rates import table_payload


class RateMetadataTests(unittest.TestCase):
    def test_stale_rates_do_not_hide_local_network_denial(self):
        from steam_price_polisher.http_client import HttpClientError, is_network_access_denied
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteCache(Path(directory) / "cache.db", clock=lambda: 100)
            cache.put_exchange_rate("USD", 4, "2026-09-08")
            http = Mock()
            http.get_json.side_effect = HttpClientError("blocked", network_access_denied=True)
            provider = CachedExchangeRateProvider(NbpExchangeRateProvider(http), cache, ttl=10, clock=lambda: 200)
            with self.assertRaises(ExchangeRateError) as raised:
                provider.get_rate_details(["USD"])
            self.assertTrue(is_network_access_denied(raised.exception))
            self.assertEqual(cache.get_exchange_rate("USD").fetched_at, 100)

    def test_nbp_retains_per_currency_dates_and_deduplicates(self):
        http = Mock()
        http.get_json.side_effect = [
            table_payload("A", "2026-09-08", USD=4),
            table_payload("B", "2026-09-07", AED=1),
        ]
        details = NbpExchangeRateProvider(http).get_rate_details(["usd", "USD", "AED", "PLN"])
        self.assertEqual(details["USD"].effective_date, "2026-09-08")
        self.assertEqual(details["AED"].effective_date, "2026-09-07")
        self.assertEqual(details["AED"].source, "NBP table B (mid)")
        self.assertEqual(details["PLN"].source, "Identity conversion")
        self.assertEqual(http.get_json.call_count, 2)

    def test_invalid_nbp_metadata_and_values_are_rejected(self):
        cases = [(4, None), (4, "2026-02-30"), (4, "20260908"),
                 (float("nan"), "2026-09-08"), (float("inf"), "2026-09-08"),
                 (True, "2026-09-08"), (0, "2026-09-08")]
        for value, day in cases:
            with self.subTest(value=value, day=day):
                http = Mock()
                http.get_json.return_value = table_payload("A", day, USD=value)
                with self.assertRaises(ExchangeRateError):
                    NbpExchangeRateProvider(http).get_rate_details(["USD"])
        http.get_json.return_value = table_payload("B", USD=4)
        with self.assertRaises(ExchangeRateError):
            NbpExchangeRateProvider(http).get_rate_table("A")

    def test_dates_survive_cache_reopen_and_stale_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            cache = SQLiteCache(path, clock=lambda: 100)
            upstream = Mock()
            upstream.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4, "2026-09-08")}
            first = CachedExchangeRateProvider(upstream, cache, clock=lambda: 100).get_rate_details(["USD"])
            reopened = SQLiteCache(path, clock=lambda: 200)
            warm = CachedExchangeRateProvider(upstream, reopened, clock=lambda: 101).get_rate_details(["USD"])
            self.assertEqual(upstream.get_rate_details.call_count, 1)
            self.assertEqual(warm["USD"].cache_status, "cache")
            upstream.get_rate_details.side_effect = ExchangeRateError("offline")
            stale = CachedExchangeRateProvider(upstream, reopened, ttl=10, clock=lambda: 200).get_rate_details(["USD"])
            self.assertEqual(stale["USD"].effective_date, first["USD"].effective_date)
            self.assertEqual(stale["USD"].cache_status, "stale cache")
            self.assertEqual(reopened.get_exchange_rate("USD").fetched_at, 100)
            with self.assertRaises(ExchangeRateError):
                CachedExchangeRateProvider(upstream, reopened).get_rate_details(["EUR"])

    def test_legacy_cache_date_is_unknown_and_refresh_is_attempted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            with closing(sqlite3.connect(path)) as conn:
                with conn:
                    conn.execute("CREATE TABLE exchange_rates (currency TEXT PRIMARY KEY, rate_to_pln REAL NOT NULL, fetched_at REAL NOT NULL)")
                    conn.execute("INSERT INTO exchange_rates VALUES ('USD', 4, 100)")
            cache = SQLiteCache(path)
            self.assertIsNone(cache.get_exchange_rate("USD").effective_date)
            upstream = Mock()
            upstream.get_rate_details.side_effect = ExchangeRateError("offline")
            provider = CachedExchangeRateProvider(upstream, cache, clock=lambda: 101)
            detail = provider.get_rate_details(["USD"])["USD"]
            self.assertIsNone(detail.effective_date)
            self.assertEqual(detail.cache_status, "stale cache")
            upstream.get_rate_details.side_effect = None
            upstream.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4.1, "2026-09-08")}
            provider.get_rate_details(["USD"])
            self.assertEqual(cache.get_exchange_rate("USD").effective_date, "2026-09-08")

    def test_results_show_methodology_dates_and_unknown_stale_rates(self):
        stream = io.StringIO()
        result = AnalysisResult((), (), (
            ExchangeRate("USD", 4, None, cache_status="stale cache"),
            ExchangeRate("EUR", 4.2, "2026-09-08", cache_status="cache"),
        ), ComparisonMethodology())
        ConsolePresenter(stream, use_colors=False).show_results(result)
        output = stream.getvalue()
        for expected in ("effective unknown", "2026-09-08", "stale cache", "NBP table A", "VAT", "Germany", "fees", "not a complete judgment"):
            self.assertIn(expected, output)


if __name__ == "__main__":
    unittest.main()
