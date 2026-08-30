import unittest
from urllib.parse import parse_qs, urlparse

from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.models import PriceStatus
from steam_price_polisher.steam_access import (
    SteamClient,
    SteamProtocolError,
    SteamRegionMismatchError,
    SteamTemporaryError,
    normalize_steam_identifier,
)


class QueueHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get_json(self, url, headers=None):
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class SteamAccessTests(unittest.TestCase):
    def test_normalizes_supported_identifiers(self):
        examples = {
            "76561198000000000": "76561198000000000",
            "https://steamcommunity.com/profiles/76561198000000000/": "76561198000000000",
            "https://steamcommunity.com/id/example/?x=1": "example",
            "https://store.steampowered.com/wishlist/id/example/": "example",
        }
        for value, expected in examples.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_steam_identifier(value), expected)

    def test_reads_wishlist_from_web_api(self):
        http = QueueHttpClient(
            [{"response": {"items": [{"appid": 10}, {"appid": 20}]}}]
        )
        client = SteamClient(http, request_delay=0, sleep=lambda _: None)

        result = client.get_wishlist("76561198000000000")

        self.assertEqual([item.app_id for item in result.items], ["10", "20"])
        self.assertEqual(result.source, "Steam Web API")
        query = parse_qs(urlparse(http.urls[0]).query)
        self.assertEqual(query["steamid"], ["76561198000000000"])

    def test_reads_regional_price_and_name(self):
        http = QueueHttpClient(
            [
                {
                    "10": {
                        "success": True,
                        "data": {
                            "name": "Test Game",
                            "price_overview": {"final": 4999, "currency": "PLN"},
                        },
                    }
                }
            ]
        )
        client = SteamClient(http, request_delay=0, sleep=lambda _: None)

        result = client.get_regional_price("10", "pl", "PLN")

        self.assertEqual(result.status, PriceStatus.AVAILABLE)
        self.assertEqual(result.game_name, "Test Game")
        self.assertEqual(result.price.amount, 49.99)
        self.assertEqual(result.price.currency, "PLN")

    def test_success_false_is_an_explicit_unavailable_result(self):
        client = SteamClient(
            QueueHttpClient([{"10": {"success": False}}]),
            request_delay=0,
            sleep=lambda _: None,
        )

        result = client.get_regional_price("10", "pl", "PLN")

        self.assertEqual(result.status, PriceStatus.APP_UNAVAILABLE)
        self.assertIsNone(result.price)

    def test_valid_data_without_price_is_not_a_protocol_failure(self):
        client = SteamClient(
            QueueHttpClient(
                [{"10": {"success": True, "data": {"name": "Free Game"}}}]
            ),
            request_delay=0,
            sleep=lambda _: None,
        )

        result = client.get_regional_price("10", "pl", "PLN")

        self.assertEqual(result.status, PriceStatus.NO_REGIONAL_PRICE)
        self.assertEqual(result.game_name, "Free Game")

    def test_missing_app_key_is_a_protocol_failure(self):
        client = SteamClient(
            QueueHttpClient([{}]),
            request_delay=0,
            sleep=lambda _: None,
        )

        with self.assertRaises(SteamProtocolError):
            client.get_regional_price("10", "pl", "PLN")

    def test_malformed_final_price_is_a_protocol_failure(self):
        client = SteamClient(
            QueueHttpClient(
                [
                    {
                        "10": {
                            "success": True,
                            "data": {
                                "name": "Broken Game",
                                "price_overview": {
                                    "final": "4999",
                                    "currency": "PLN",
                                },
                            },
                        }
                    }
                ]
            ),
            request_delay=0,
            sleep=lambda _: None,
        )

        with self.assertRaises(SteamProtocolError):
            client.get_regional_price("10", "pl", "PLN")

    def test_currency_mismatch_is_reported_separately(self):
        client = SteamClient(
            QueueHttpClient(
                [
                    {
                        "10": {
                            "success": True,
                            "data": {
                                "name": "Wrong Region",
                                "price_overview": {
                                    "final": 4999,
                                    "currency": "USD",
                                },
                            },
                        }
                    }
                ]
            ),
            request_delay=0,
            sleep=lambda _: None,
        )

        with self.assertRaises(SteamRegionMismatchError):
            client.get_regional_price("10", "pl", "PLN")

    def test_exhausted_transient_http_failure_remains_retryable(self):
        client = SteamClient(
            QueueHttpClient(
                [HttpClientError("rate limited", status_code=429, transient=True)]
            ),
            request_delay=0,
            sleep=lambda _: None,
        )

        with self.assertRaises(SteamTemporaryError) as raised:
            client.get_regional_price("10", "pl", "PLN")

        self.assertTrue(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
