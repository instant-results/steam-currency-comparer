import tempfile
import unittest
from pathlib import Path

from steam_price_polisher.analysis import AnalysisRunner, RegionConfig
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
