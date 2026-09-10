import tempfile
import unittest
from pathlib import Path

from steam_price_polisher.analysis import AnalysisRunner, RegionConfig, order_wishlist_items
from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.models import (
    AnalysisResult,
    RegionalPriceResult,
    SkipCategory,
    StorePrice,
    WishlistItem,
)
from steam_price_polisher.price_service import CachedPriceService
from steam_price_polisher.steam_access import SteamTemporaryError


class FlakyPriceProvider:
    def __init__(self):
        self.calls = []
        self.failed_once = False

    def get_regional_price(self, app_id, region, expected_currency):
        self.calls.append((app_id, region))
        if region == "us" and not self.failed_once:
            self.failed_once = True
            raise SteamTemporaryError(
                "temporary USD failure",
                app_id=app_id,
                region=region,
            )
        prices = {"pl": 40.0, "us": 10.0, "de": 12.0}
        return RegionalPriceResult.available(
            StorePrice(region, expected_currency, prices[region]),
            "Test Game",
        )


class AnalysisTests(unittest.TestCase):
    def test_orders_wishlist_by_priority_date_and_known_name(self):
        wishlist = (
            WishlistItem("10", "Zulu", date_added=100, priority=2),
            WishlistItem("20", "Alpha", date_added=300, priority=0),
            WishlistItem("30", "Beta"),
        )

        self.assertEqual(
            [item.app_id for item in order_wishlist_items(wishlist, "priority")],
            ["20", "10", "30"],
        )
        self.assertEqual(
            [item.app_id for item in order_wishlist_items(wishlist, "date_added")],
            ["20", "10", "30"],
        )
        self.assertEqual(
            [item.app_id for item in order_wishlist_items(wishlist, "name")],
            ["20", "30", "10"],
        )

    def test_name_order_prefetches_each_baseline_once_and_reuses_it(self):
        class NamedProvider:
            def __init__(self):
                self.calls = []

            def get_regional_price(self, app_id, region, expected_currency):
                self.calls.append((app_id, region))
                names = {"10": "Zulu", "20": "Alpha"}
                return RegionalPriceResult.available(
                    StorePrice(region, expected_currency, 10),
                    names[app_id],
                )

        with tempfile.TemporaryDirectory() as directory:
            provider = NamedProvider()
            runner = AnalysisRunner(
                CachedPriceService(provider, SQLiteCache(Path(directory) / "cache.sqlite3")),
                home=RegionConfig("pl", "PLN"),
                alternatives=(RegionConfig("us", "USD"),),
            )
            progress = tuple(
                runner.run(
                    (WishlistItem("10"), WishlistItem("20")),
                    {"USD": 4.0},
                    order="name",
                )
            )

        self.assertEqual([item.app_id for item in progress], ["20", "10"])
        self.assertEqual(provider.calls.count(("10", "pl")), 1)
        self.assertEqual(provider.calls.count(("20", "pl")), 1)
        self.assertTrue(all(item.live_requests == 2 for item in progress))

    def test_interrupted_game_resumes_from_cached_regions(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteCache(Path(directory) / "cache.sqlite3")
            live = FlakyPriceProvider()
            service = CachedPriceService(live, cache)
            runner = AnalysisRunner(
                service,
                home=RegionConfig("pl", "PLN"),
                alternatives=(
                    RegionConfig("us", "USD"),
                    RegionConfig("de", "EUR"),
                ),
            )
            wishlist = (WishlistItem("10"),)
            rates = {"USD": 4.0, "EUR": 4.5}

            first = tuple(runner.run(wishlist, rates))[0]
            second = tuple(runner.run(wishlist, rates))[0]

        self.assertIsNotNone(first.skipped)
        self.assertEqual(first.skipped.category, SkipCategory.TEMPORARY_FAILURE)
        self.assertTrue(first.skipped.retryable)
        self.assertIsNotNone(second.comparison)
        self.assertEqual(second.cache_hits, 1)
        self.assertEqual(second.live_requests, 2)
        self.assertEqual(second.comparison.home_price.source, "cache")
        self.assertEqual([p.source for p in second.comparison.alternatives], ["live", "live"])
        self.assertEqual(live.calls.count(("10", "pl")), 1)

    def test_valid_missing_price_does_not_make_the_run_partial(self):
        class MissingPriceProvider:
            def get_regional_price(self, app_id, region, expected_currency):
                return RegionalPriceResult.no_regional_price(
                    "Unavailable Game",
                    "Steam supplied no regional price.",
                )

        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteCache(Path(directory) / "cache.sqlite3")
            runner = AnalysisRunner(
                CachedPriceService(MissingPriceProvider(), cache),
                home=RegionConfig("pl", "PLN"),
                alternatives=(RegionConfig("us", "USD"),),
            )
            progress = tuple(
                runner.run((WishlistItem("10"),), {"USD": 4.0})
            )[0]

        result = AnalysisResult((), (progress.skipped,))
        self.assertEqual(progress.skipped.category, SkipCategory.NO_REGIONAL_PRICE)
        self.assertFalse(result.is_partial)


if __name__ == "__main__":
    unittest.main()
