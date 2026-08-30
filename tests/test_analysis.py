import tempfile
import unittest
from pathlib import Path

from steam_price_polisher.analysis import AnalysisRunner, RegionConfig
from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.models import RegionalPriceResult, StorePrice, WishlistItem
from steam_price_polisher.price_service import CachedPriceService
from steam_price_polisher.steam_access import SteamAccessError


class FlakyPriceProvider:
    def __init__(self):
        self.calls = []
        self.failed_once = False

    def get_regional_price(self, app_id, region, expected_currency):
        self.calls.append((app_id, region))
        if region == "us" and not self.failed_once:
            self.failed_once = True
            raise SteamAccessError("temporary USD failure")
        prices = {"pl": 40.0, "us": 10.0, "de": 12.0}
        return RegionalPriceResult(
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
        self.assertIsNotNone(second.comparison)
        self.assertEqual(second.cache_hits, 1)
        self.assertEqual(second.live_requests, 2)
        self.assertEqual(live.calls.count(("10", "pl")), 1)


if __name__ == "__main__":
    unittest.main()
