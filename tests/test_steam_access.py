import unittest
from urllib.parse import parse_qs, urlparse

from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.models import PriceStatus, WishlistFailure
from steam_price_polisher.steam_access import (
    SteamClient,
    SteamProtocolError,
    SteamRegionMismatchError,
    SteamTemporaryError,
    VanityResolutionStatus,
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
    def test_denied_wishlist_does_not_retry_another_endpoint(self):
        for identifier, key in (("76561198000000000", ""), ("example", "secret"), ("example", "")):
            http = QueueHttpClient([HttpClientError("private", network_access_denied=True)])
            client = SteamClient(http, web_api_key=key)
            result = client.get_wishlist(identifier)
            self.assertEqual(result.failure, WishlistFailure.NETWORK_ACCESS_DENIED)
            self.assertEqual(len(http.urls), 1)
            self.assertNotIn("private", str(result))

    def test_regional_network_denial_retains_category_and_is_not_retryable(self):
        from steam_price_polisher.steam_access import SteamAccessError
        from steam_price_polisher.models import SkipCategory
        http = QueueHttpClient([HttpClientError("private", network_access_denied=True)])
        with self.assertRaises(SteamAccessError) as raised:
            SteamClient(http, request_delay=0).get_regional_price("10", "pl", "PLN")
        self.assertEqual(raised.exception.category, SkipCategory.NETWORK_ACCESS_DENIED)
        self.assertFalse(raised.exception.retryable)
        self.assertNotIn("private", str(raised.exception))

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
            [{"response": {"items": [
                {"appid": 10, "priority": 2, "date_added": 1700000000},
                {"appid": 20, "priority": 0, "date_added": 1800000000},
            ]}}]
        )
        client = SteamClient(http, request_delay=0, sleep=lambda _: None)

        result = client.get_wishlist("76561198000000000")

        self.assertEqual([item.app_id for item in result.items], ["10", "20"])
        self.assertEqual([item.priority for item in result.items], [2, 0])
        self.assertEqual([item.date_added for item in result.items], [1700000000, 1800000000])
        self.assertEqual(result.source, "Steam Web API")
        query = parse_qs(urlparse(http.urls[0]).query)
        self.assertEqual(query["steamid"], ["76561198000000000"])

    def test_resolves_vanity_name_with_configured_api_key(self):
        http = QueueHttpClient(
            [
                {
                    "response": {
                        "success": 1,
                        "steamid": "76561198000000000",
                    }
                },
                {"response": {"items": [{"appid": 10}]}},
            ]
        )
        client = SteamClient(
            http,
            request_delay=0,
            sleep=lambda _: None,
            web_api_key="secret-key",
        )

        result = client.get_wishlist("https://steamcommunity.com/id/example")

        self.assertEqual([item.app_id for item in result.items], ["10"])
        vanity_query = parse_qs(urlparse(http.urls[0]).query)
        self.assertEqual(vanity_query["key"], ["secret-key"])
        self.assertEqual(vanity_query["vanityurl"], ["example"])
        self.assertEqual(vanity_query["url_type"], ["1"])
        wishlist_query = parse_qs(urlparse(http.urls[1]).query)
        self.assertEqual(wishlist_query["steamid"], ["76561198000000000"])

    def test_vanity_without_api_key_skips_numeric_web_api(self):
        http = QueueHttpClient([{}])
        client = SteamClient(http, request_delay=0, sleep=lambda _: None)

        result = client.get_wishlist("example")

        self.assertEqual(result.items, ())
        self.assertIn("STEAM_WEB_API_KEY", result.warnings[0])
        self.assertEqual(len(http.urls), 1)
        self.assertIn("/wishlist/id/example/", http.urls[0])

    def test_unknown_vanity_name_has_a_specific_result(self):
        client = SteamClient(
            QueueHttpClient(
                [{"response": {"success": 42, "message": "No match"}}]
            ),
            request_delay=0,
            sleep=lambda _: None,
            web_api_key="secret-key",
        )

        result = client.resolve_vanity_url("missing-profile")

        self.assertEqual(result.status, VanityResolutionStatus.NOT_FOUND)
        self.assertIsNone(result.steam_id)
        self.assertIn("No match", result.message)

    def test_invalid_vanity_response_is_distinguished(self):
        client = SteamClient(
            QueueHttpClient([{"unexpected": True}]),
            request_delay=0,
            sleep=lambda _: None,
            web_api_key="secret-key",
        )

        result = client.resolve_vanity_url("example")

        self.assertEqual(result.status, VanityResolutionStatus.INVALID_RESPONSE)

    def test_vanity_request_failure_does_not_expose_api_key(self):
        client = SteamClient(
            QueueHttpClient(
                [
                    HttpClientError(
                        "HTTP 401 for https://example.test?key=secret-key"
                    )
                ]
            ),
            request_delay=0,
            sleep=lambda _: None,
            web_api_key="secret-key",
        )

        result = client.resolve_vanity_url("example")

        self.assertEqual(result.status, VanityResolutionStatus.REQUEST_FAILED)
        self.assertNotIn("secret-key", result.message)

    def test_tls_failure_is_not_an_empty_wishlist(self):
        http = QueueHttpClient([HttpClientError("private details", tls_error=True)] * 2)
        result = SteamClient(http).get_wishlist("https://steamcommunity.com/profiles/76561198000000000/")
        self.assertEqual(result.failure, WishlistFailure.TLS)
        self.assertNotIn("private details", str(result))

    def test_explicit_empty_wishlist_is_not_a_failure(self):
        result = SteamClient(QueueHttpClient([{"response": {"items": []}}])).get_wishlist("76561198000000000")
        self.assertEqual(result.items, ())
        self.assertIsNone(result.failure)

    def test_malformed_api_is_not_reported_as_empty(self):
        result = SteamClient(QueueHttpClient([{"response": {"items": "broken"}}, {}])).get_wishlist("76561198000000000")
        self.assertEqual(result.failure, WishlistFailure.INVALID_RESPONSE)

    def test_valid_fallback_recovers_from_api_failure(self):
        result = SteamClient(QueueHttpClient([HttpClientError("offline"), {"10": {"name": "Game", "priority": 3, "date_added": 1700000000}}])).get_wishlist("76561198000000000")
        self.assertIsNone(result.failure)
        self.assertEqual(result.items[0].app_id, "10")
        self.assertEqual(result.items[0].priority, 3)
        self.assertEqual(result.items[0].date_added, 1700000000)

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

    def test_free_product_is_distinct_from_missing_paid_price(self):
        client = SteamClient(QueueHttpClient([
            {"10": {"success": True, "data": {"name": "Demo", "is_free": True}}},
            {"11": {"success": True, "data": {"name": "Unreleased game", "is_free": False}}},
        ]), request_delay=0, sleep=lambda _: None)
        free = client.get_regional_price("10", "pl", "PLN")
        missing = client.get_regional_price("11", "pl", "PLN")
        self.assertEqual(free.status, PriceStatus.NO_REGIONAL_PRICE)
        self.assertTrue(free.is_free)
        self.assertEqual(missing.status, PriceStatus.NO_REGIONAL_PRICE)
        self.assertFalse(missing.is_free)

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
