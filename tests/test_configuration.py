import unittest
from steam_price_polisher.models import ExchangeRate
from unittest.mock import Mock, patch

from steam_price_polisher.configuration import ComparisonConfig, RegionConfig
from steam_price_polisher.analysis import AnalysisRunner
from steam_price_polisher.models import WishlistItem, WishlistResult
import steam_wishlist_compare as cli


class ConfigurationTests(unittest.TestCase):
    def test_defaults_and_normalization(self):
        self.assertEqual(ComparisonConfig().currencies, ("USD", "EUR"))
        config = ComparisonConfig.from_regions([" DE ", "US"])
        self.assertEqual(config.currencies, ("EUR", "USD"))
        self.assertEqual(RegionConfig(" PL ", " pln "), config.home)

    def test_invalid_selections(self):
        for regions in ([], ["us", "US"], ["pl"], ["fr"], ["USD"], ["us"] * 37, "us"):
            with self.subTest(regions=regions), self.assertRaises(ValueError):
                ComparisonConfig.from_regions(regions)
        with self.assertRaises(ValueError):
            RegionConfig("us", "EUR")
        with self.assertRaises(ValueError):
            ComparisonConfig(home=RegionConfig("us", "USD"))

    def test_copies_mutable_selection(self):
        regions = [RegionConfig("de", "EUR")]
        config = ComparisonConfig(alternatives=regions)
        regions.clear()
        self.assertEqual(config.currencies, ("EUR",))

    def test_runner_rejects_home_as_alternative(self):
        with self.assertRaises(ValueError):
            AnalysisRunner(Mock(), home=RegionConfig("pl", "PLN"),
                           alternatives=[RegionConfig("pl", "PLN")])


class ConfigurationCliTests(unittest.TestCase):
    def test_invalid_configuration_does_not_initialize_io(self):
        with patch.object(cli, "UrllibJsonHttpClient") as http, \
             patch.object(cli, "SQLiteCache") as cache, \
             patch.object(cli, "ConsolePresenter"):
            self.assertEqual(cli.main(["123", "--regions", "pl"]), 1)
            http.assert_not_called()
            cache.assert_not_called()

    def test_help_does_not_initialize_io(self):
        with patch.object(cli, "UrllibJsonHttpClient") as http, \
             patch("sys.stdout"):
            self.assertEqual(cli.main(["--help"]), 0)
            http.assert_not_called()

    def test_selected_region_drives_rates_and_price_requests(self):
        from steam_price_polisher.models import RegionalPriceResult, StorePrice
        from steam_price_polisher.price_service import PriceLookup
        with patch.object(cli, "UrllibJsonHttpClient"), \
             patch.object(cli, "SQLiteCache"), \
             patch.object(cli, "CachedExchangeRateProvider") as rates, \
             patch.object(cli, "SteamClient") as steam, \
             patch.object(cli, "CachedPriceService") as prices, \
             patch.object(cli, "ConsolePresenter"):
            rates.return_value.get_rate_details.return_value = {"EUR": ExchangeRate("EUR", 4.0, "2026-09-08")}
            steam.return_value.get_wishlist.return_value = WishlistResult(
                (WishlistItem("10", "Game"),), "test"
            )
            prices.return_value.get_regional_price.side_effect = [
                PriceLookup(RegionalPriceResult.available(StorePrice("pl", "PLN", 40), "Game"), "live"),
                PriceLookup(RegionalPriceResult.available(StorePrice("de", "EUR", 12), "Game"), "live"),
            ]
            self.assertEqual(cli.main(["123", "--regions", "de"]), 0)
            rates.return_value.get_rate_details.assert_called_once_with(("EUR",))
            self.assertEqual(
                [call.args for call in prices.return_value.get_regional_price.call_args_list],
                [("10", "pl", "PLN"), ("10", "de", "EUR")],
            )


if __name__ == "__main__":
    unittest.main()
