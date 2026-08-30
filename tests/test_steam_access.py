import unittest
from urllib.parse import parse_qs, urlparse

from steam_price_polisher.steam_access import SteamClient, normalize_steam_identifier


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
                            "price_overview": {"final": 4999},
                        },
                    }
                }
            ]
        )
        client = SteamClient(http, request_delay=0, sleep=lambda _: None)

        result = client.get_regional_price("10", "pl", "PLN")

        self.assertEqual(result.game_name, "Test Game")
        self.assertEqual(result.price.amount, 49.99)
        self.assertEqual(result.price.currency, "PLN")


if __name__ == "__main__":
    unittest.main()
