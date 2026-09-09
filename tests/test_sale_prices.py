import tempfile
import unittest
from pathlib import Path

from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.comparison import compare_game
from steam_price_polisher.models import StorePrice, RegionalPriceResult
from steam_price_polisher.steam_access import SteamClient, SteamProtocolError
from tests.test_steam_access import QueueHttpClient


class SalePriceTests(unittest.TestCase):
    def fetch(self, initial, discount, final=500):
        overview = {"currency": "PLN", "final": final, "initial": initial, "discount_percent": discount}
        return SteamClient(QueueHttpClient([{"10": {"success": True, "data": {"price_overview": overview}}}]), request_delay=0).get_regional_price("10", "pl", "PLN")

    def test_preserves_base_final_and_discount(self):
        result = self.fetch(1000, 50)
        self.assertEqual(result.price, StorePrice("pl", "PLN", 5, 10, 50))

    def test_zero_discount_is_known_not_on_sale(self):
        self.assertEqual(self.fetch(500, 0).price.discount_percent, 0)

    def test_missing_sale_metadata_remains_unknown(self):
        result = self.fetch(None, None)
        self.assertIsNone(result.price.base_amount)
        self.assertIsNone(result.price.discount_percent)

    def test_invalid_metadata_is_rejected(self):
        for initial, discount in [(400, 50), (float("nan"), 50), (True, 20), (1000, True), (1000, 101), (1000, -1)]:
            with self.subTest(initial=initial, discount=discount), self.assertRaises(SteamProtocolError):
                self.fetch(initial, discount)

    def test_cache_preserves_sale_metadata_per_region(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteCache(Path(directory) / "cache.db")
            prices = [StorePrice("pl", "PLN", 50, 100, 50), StorePrice("us", "USD", 15, 20, 25)]
            for price in prices:
                cache.put_price("10", price.region, price.currency, RegionalPriceResult.available(price, "Game"))
            reopened = SQLiteCache(Path(directory) / "cache.db")
            for price in prices:
                self.assertEqual(reopened.get_price("10", price.region, price.currency).result.price, price)

    def test_comparison_uses_final_prices_and_keeps_independent_discounts(self):
        result = compare_game("10", "Game", StorePrice("pl", "PLN", 50, 100, 50),
                              [StorePrice("us", "USD", 15, 20, 25), StorePrice("de", "EUR", 10, 10, 0)],
                              {"USD": 4, "EUR": 4.5})
        self.assertFalse(result.is_fair)
        self.assertEqual(result.alternatives[0].amount_in_home, 60)
        self.assertEqual([p.discount_percent for p in result.alternatives], [25, 0])
        self.assertEqual(result.alternatives[0].base_amount, 20)

    def test_legacy_price_refreshes_to_get_sale_metadata(self):
        from unittest.mock import Mock
        from steam_price_polisher.price_service import CachedPriceService
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteCache(Path(directory) / "cache.db", clock=lambda: 100)
            cache.put_price("10", "pl", "PLN", RegionalPriceResult.available(StorePrice("pl", "PLN", 5), "Game"))
            live = Mock()
            live.get_regional_price.return_value = self.fetch(1000, 50)
            service = CachedPriceService(live, cache, clock=lambda: 100, require_sale_metadata=True)
            result = service.get_regional_price("10", "pl", "PLN")
            self.assertEqual(result.source, "live")
            self.assertEqual(result.result.price.discount_percent, 50)
            self.assertEqual(service.get_regional_price("10", "pl", "PLN").source, "cache")
            live.get_regional_price.assert_called_once()

    def test_sale_prices_expire_earlier_than_regular_prices(self):
        from unittest.mock import Mock
        from steam_price_polisher.price_service import CachedPriceService
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteCache(Path(directory) / "cache.db", clock=lambda: 100)
            cache.put_price("10", "pl", "PLN", self.fetch(1000, 50))
            live = Mock()
            live.get_regional_price.return_value = self.fetch(1000, 0, final=1000)
            service = CachedPriceService(live, cache, clock=lambda: 1001)
            self.assertEqual(service.get_regional_price("10", "pl", "PLN").source, "live")
