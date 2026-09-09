import unittest

from steam_price_polisher.exchange_rates import ExchangeRateError, NbpExchangeRateProvider


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get_json(self, url, headers=None):
        self.urls.append(url)
        for currency, response in self.responses.items():
            if f"/{currency.lower()}/" in url:
                return response
        raise AssertionError(f"Unexpected URL: {url}")


class ExchangeRateTests(unittest.TestCase):
    def test_fetches_requested_nbp_rates(self):
        http = FakeHttpClient(
            {
                "USD": {"code": "USD", "table": "A", "rates": [{"mid": 3.75, "effectiveDate": "2026-09-08"}]},
                "EUR": {"code": "EUR", "table": "A", "rates": [{"mid": 4.25, "effectiveDate": "2026-09-07"}]},
            }
        )

        rates = NbpExchangeRateProvider(http).get_rates_to_pln(("USD", "EUR"))

        self.assertEqual(rates, {"USD": 3.75, "EUR": 4.25})
        self.assertTrue(all(url.startswith("https://") for url in http.urls))

    def test_rejects_malformed_response(self):
        provider = NbpExchangeRateProvider(FakeHttpClient({"USD": {"rates": []}}))

        with self.assertRaises(ExchangeRateError):
            provider.get_rates_to_pln(("USD",))


if __name__ == "__main__":
    unittest.main()
