from copy import deepcopy
import unittest

from steam_price_polisher.exchange_rates import ExchangeRateError, NbpExchangeRateProvider


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get_json(self, url, headers=None):
        self.urls.append(url)
        for table, response in self.responses.items():
            if f"/tables/{table.lower()}/" in url:
                if isinstance(response, Exception):
                    raise response
                return deepcopy(response)
        raise AssertionError(f"Unexpected URL: {url}")


def table_payload(table="A", day="2026-10-20", **rates):
    return [{"table": table, "no": f"test/{table}/2026", "effectiveDate": day,
             "rates": [{"code": code, "mid": value} for code, value in rates.items()]}]


class ExchangeRateTests(unittest.TestCase):
    def test_fetches_requested_nbp_rates(self):
        http = FakeHttpClient(
            {
                "A": table_payload(USD=3.75, EUR=4.25, NOK=0.4, GBP=5),
                "B": table_payload("B", AED=1),
            }
        )

        rates = NbpExchangeRateProvider(http).get_rates_to_pln(("USD", "EUR"))

        self.assertEqual(rates, {"USD": 3.75, "EUR": 4.25})
        self.assertEqual(http.urls, [f"https://api.nbp.pl/api/exchangerates/tables/{table}/?format=json"
                                     for table in ("a", "b")])

    def test_unused_table_failure_does_not_block_requested_rates(self):
        for failed, requested, expected in (("B", "USD", 4), ("A", "AED", 1)):
            with self.subTest(failed=failed):
                responses = {"A": table_payload(USD=4), "B": table_payload("B", AED=1)}
                responses[failed] = RuntimeError("offline")
                http = FakeHttpClient(responses)
                self.assertEqual(NbpExchangeRateProvider(http).get_rates_to_pln([requested]),
                                 {requested: expected})
                self.assertEqual(len(http.urls), 2)

    def test_rejects_malformed_response(self):
        provider = NbpExchangeRateProvider(FakeHttpClient({"A": {"rates": []}}))

        with self.assertRaises(ExchangeRateError):
            provider.get_rates_to_pln(("USD",))

    def test_pln_and_empty_requests_do_not_use_http(self):
        http = FakeHttpClient({})
        provider = NbpExchangeRateProvider(http)
        self.assertEqual(provider.get_rate_details([]), {})
        self.assertEqual(provider.get_rates_to_pln(["pln", "PLN"]), {"PLN": 1})
        self.assertEqual(http.urls, [])

    def test_invalid_currency_codes_are_rejected_before_http(self):
        http = FakeHttpClient({})
        for currencies in ("USD", [None], ["usd/"], [" US"], ["123"], ["USＤ"]):
            with self.subTest(currencies=currencies), self.assertRaises(ValueError):
                NbpExchangeRateProvider(http).get_rate_details(currencies)
        self.assertEqual(http.urls, [])

    def test_complete_table_validation_rejects_bad_shapes_and_duplicate_codes(self):
        good = table_payload(USD=4)
        cases = [None, {}, [], good * 2, [None], table_payload("B", USD=4),
                 table_payload(), [{**good[0], "rates": {}}],
                 [{**good[0], "rates": good[0]["rates"] * 2}],
                 table_payload(usd=4), table_payload(PLN=1), table_payload(US=4),
                 [{**good[0], "rates": [None]}]]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ExchangeRateError):
                NbpExchangeRateProvider(FakeHttpClient({"A": payload})).get_rate_table("A")

    def test_currency_absent_from_both_tables_is_explicit(self):
        http = FakeHttpClient({"A": table_payload(USD=4), "B": table_payload("B", AED=1)})
        with self.assertRaisesRegex(ExchangeRateError, "do not provide: XYZ"):
            NbpExchangeRateProvider(http).get_rate_details(["XYZ"])
        self.assertEqual(len(http.urls), 2)


if __name__ == "__main__":
    unittest.main()
