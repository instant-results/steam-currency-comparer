import unittest

from steam_price_polisher.comparison import compare_game
from steam_price_polisher.models import StorePrice


class ComparisonTests(unittest.TestCase):
    def test_home_price_is_fair_when_not_higher_than_any_alternative(self):
        result = compare_game(
            "10",
            "Test Game",
            StorePrice("pl", "PLN", 40.0),
            (StorePrice("us", "USD", 10.0), StorePrice("de", "EUR", 12.0)),
            {"USD": 4.0, "EUR": 4.5},
        )

        self.assertTrue(result.is_fair)
        self.assertAlmostEqual(result.savings, 0.0)
        self.assertEqual(result.cheapest_alternative.currency, "USD")

    def test_home_price_is_expensive_when_higher_than_one_alternative(self):
        result = compare_game(
            "20",
            "Another Game",
            StorePrice("pl", "PLN", 50.0),
            (StorePrice("us", "USD", 10.0), StorePrice("de", "EUR", 12.0)),
            {"USD": 4.0, "EUR": 4.5},
        )

        self.assertFalse(result.is_fair)
        self.assertAlmostEqual(result.overpayment, 10.0)

    def test_missing_exchange_rate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing exchange rate for EUR"):
            compare_game(
                "30",
                "Missing Rate",
                StorePrice("pl", "PLN", 50.0),
                (StorePrice("de", "EUR", 12.0),),
                {"USD": 4.0},
            )


if __name__ == "__main__":
    unittest.main()
