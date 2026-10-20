from tests.batch_fixtures import mock_batch_prices
from tests.test_exchange_rates import table_payload
import io
import json
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.models import RegionalPriceResult, StorePrice
from steam_price_polisher.owned_library import LibraryAccessError, parse_owned_library
from steam_price_polisher.steam_access import SteamClient
from steam_price_polisher.web_app import JobManager, WebApplication, InputError, validate_library_request

PROFILE = "76561198000000000"  # Documentation placeholder; no real user profile.


class LibraryAccessTests(unittest.TestCase):
    def test_owned_games_request_uses_public_host_appinfo_and_excludes_free_games(self):
        http = Mock()
        http.get_json.return_value = {"response": {"game_count": 2, "games": [
            {"appid": 20, "name": "Zebra"}, {"appid": 10, "name": "Alpha"}]}}
        client = SteamClient(http, web_api_key="test-only-key")
        result = client.get_owned_library(PROFILE)
        self.assertEqual([item.app_id for item in result.items], ["20", "10"])
        url = urlsplit(http.get_json.call_args.args[0])
        self.assertEqual(url.netloc, "api.steampowered.com")
        self.assertEqual(url.path, "/IPlayerService/GetOwnedGames/v1/")
        query = parse_qs(url.query)
        self.assertEqual(query["key"], ["test-only-key"])
        self.assertEqual(json.loads(query["input_json"][0]), {
            "steamid": PROFILE, "include_appinfo": True, "include_played_free_games": False})
        self.assertEqual(http.get_json.call_count, 1)  # No fabricated pagination.

    def test_missing_key_makes_no_request_and_never_reads_local_wishlist(self):
        http = Mock()
        with self.assertRaises(LibraryAccessError) as caught:
            SteamClient(http).get_owned_library(PROFILE)
        self.assertEqual(caught.exception.code, "api_key_missing")
        http.get_json.assert_not_called()

    def test_private_unavailable_is_distinct_from_explicit_empty(self):
        for empty in [{"game_count": 0}, {"game_count": 0, "games": []}]:
            self.assertEqual(parse_owned_library({"response": empty}).items, ())
        with self.assertRaises(LibraryAccessError) as caught:
            parse_owned_library({"response": {}})
        self.assertEqual(caught.exception.code, "library_unavailable")

    def test_rejects_malformed_or_partial_payloads(self):
        for response in [None, {}, {"response": []}, {"response": {"game_count": True}},
                         {"response": {"game_count": 1}},
                         {"response": {"game_count": 2, "games": [{"appid": 10}]}},
                         *({"response": {"game_count": 1, "games": [game]}} for game in [
                             {"appid": True}, {"appid": -1}, {"appid": "10"}, {"appid": 10, "name": []}, "game"])]:
            with self.subTest(response=response), self.assertRaises(LibraryAccessError):
                parse_owned_library(response)

    def test_vanity_resolves_before_library_and_missing_names_are_preserved(self):
        http = Mock()
        http.get_json.side_effect = [{"response": {"success": 1, "steamid": PROFILE}},
                                    {"response": {"game_count": 1, "games": [{"appid": 10}]}}]
        result = SteamClient(http, web_api_key="test-only-key").get_owned_library("https://steamcommunity.com/id/example/")
        self.assertIsNone(result.items[0].name)
        self.assertEqual(http.get_json.call_count, 2)
        self.assertEqual(json.loads(parse_qs(urlsplit(http.get_json.call_args.args[0]).query)["input_json"][0])["steamid"], PROFILE)

    def test_http_errors_are_controlled_without_secret_or_upstream_text(self):
        for error, code in [(HttpClientError("private secret URL", status_code=401), "api_key_rejected"),
                            (HttpClientError("private secret URL", status_code=403), "api_key_rejected"),
                            (HttpClientError("private secret URL", transient=True), "request"),
                            (HttpClientError("private secret URL", tls_error=True), "tls"),
                            (HttpClientError("private secret URL", invalid_response=True), "invalid_response"),
                            (HttpClientError("private secret URL", network_access_denied=True), "network_access_denied")]:
            http = Mock(); http.get_json.side_effect = error
            with self.subTest(code=code), self.assertRaises(LibraryAccessError) as caught:
                SteamClient(http, web_api_key="test-only-key").get_owned_library(PROFILE)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn("test-only-key", str(caught.exception))


class LibraryJobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.manager = JobManager(self.directory.name, api_key="test-only-key", start_worker=False)
        self.manager.gate = Mock()
        self.app = WebApplication(self.manager, owned_library_enabled=True)

    def request(self, path, method="GET", body=None, token="", **overrides):
        raw = json.dumps(body).encode() if body is not None else b""
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "HTTP_HOST": "127.0.0.1:8765",
               "HTTP_ORIGIN": "http://127.0.0.1:8765", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
               "HTTP_AUTHORIZATION": "Bearer " + token, "REMOTE_ADDR": "test", **overrides}
        result = {}
        def respond(status, headers):
            result["status"] = int(status.split()[0])
        result["data"] = json.loads(b"".join(self.app(env, respond)))
        return result

    def submit(self, order="name"):
        response = self.request("/api/library-jobs", "POST", {"identifier": PROFILE, "regions": ["us"], "order": order})
        self.assertEqual(response["status"], 202)
        return self.manager.jobs[response["data"]["id"]]

    def test_profile_validation_and_library_orders(self):
        for identifier in [PROFILE, f"https://steamcommunity.com/profiles/{PROFILE}", "https://steamcommunity.com/id/example"]:
            validate_library_request({"identifier": identifier, "regions": ["us"]})
        for extra in [{"identifier": "example"}, {"identifier": f"https://store.steampowered.com/wishlist/profiles/{PROFILE}"},
                      {"order": "date_added"}, {"order": []}, {"key": "secret"}, {"regions": []}]:
            with self.subTest(extra=extra), self.assertRaises(InputError):
                validate_library_request({"identifier": PROFILE, "regions": ["us"], **extra})
        job = self.submit("steam")
        self.assertEqual(job.order, "priority")
        self.assertEqual(job.snapshot()["order"], "steam")
        self.assertEqual(job.snapshot()["source"], "library")

    def test_tokens_origin_and_shared_owner_lock_apply_to_library(self):
        self.assertEqual(self.request("/api/library-jobs", "POST", {"identifier": PROFILE,"regions": ["us"]}, HTTP_ORIGIN="https://evil.test")["status"], 403)
        job = self.submit()
        self.assertEqual(self.request("/api/jobs/" + job.id)["status"], 404)
        self.assertEqual(self.request("/api/jobs", "POST", {"identifier": PROFILE, "regions": ["us"]})["status"], 429)
        self.request("/api/jobs/" + job.id + "/cancel", "POST", {}, job.token)
        self.manager.execute(job)
        self.assertEqual(job.snapshot()["state"], "cancelled")

    def test_complete_library_comparison_orders_deduplicates_and_reuses_cache(self):
        calls = []
        def upstream(url, headers=None):
            calls.append(url)
            if "GetOwnedGames" in url:
                return {"response": {"game_count": 3, "games": [{"appid": 20,"name": "Zebra"}, {"appid": 10,"name": "Alpha"}, {"appid": 10,"name": "Alpha"}]}}
            return (table_payload("B", "2026-09-02", AED=1) if "/tables/b/" in url else
                    table_payload("A", "2026-09-08", USD=4, EUR=4))
        def price(app_id, region, currency):
            return replace(RegionalPriceResult.available(StorePrice(region,currency,10,10,0), "Alpha" if app_id == "10" else "Zebra"), developers=("Studio",), publishers=("Publisher",))
        with patch("steam_price_polisher.web_app.UrllibJsonHttpClient") as factory, patch.object(SteamClient,"get_regional_price",side_effect=price) as prices, mock_batch_prices(prices):
            factory.return_value.get_json.side_effect = upstream
            first = self.submit(); self.manager.execute(first)
            self.assertEqual(first.snapshot()["state"], "complete")
            self.assertEqual([item["app_id"] for item in first.snapshot()["items"]], ["10","20"])
            self.assertEqual(first.snapshot()["total"], 2)
            self.assertEqual(prices.call_count,4)
            # Avoid submission rate-limit coupling; second job is another owner.
            second = self.manager.submit(PROFILE,ComparisonConfig.from_regions(["us"]),"second",order="priority",library=True)
            self.manager.execute(second)
            self.assertEqual([item["app_id"] for item in second.snapshot()["items"]], ["20","10"])
            self.assertEqual(prices.call_count,4)
            self.assertEqual(sum("GetOwnedGames" in url for url in calls),2)
            self.assertNotIn("test-only-key",json.dumps(second.snapshot()))

    def test_empty_private_missing_key_and_oversize_stop_before_prices_or_rates(self):
        scenarios = [("", {}, "api_key_missing", "failed"),
                     ("test-only-key", {"response": {}}, "library_unavailable", "failed"),
                     ("test-only-key", {"response": {"game_count": 0}}, None, "complete"),
                     ("test-only-key", {"response": {"game_count": 2,"games": [{"appid": 1}, {"appid": 2}]}}, "library_limit", "failed")]
        for key, payload, code, state in scenarios:
            manager = JobManager(self.directory.name,api_key=key,max_games=1,start_worker=False); manager.gate = Mock()
            job = manager.submit(PROFILE,ComparisonConfig(),"test",order="name",library=True)
            with patch("steam_price_polisher.web_app.UrllibJsonHttpClient") as factory, patch("steam_price_polisher.web_app.CachedExchangeRateProvider") as rates:
                factory.return_value.get_json.return_value = payload
                manager.execute(job)
                self.assertEqual(job.snapshot()["state"],state)
                self.assertEqual(job.snapshot().get("error_code"),code)
                self.assertEqual(job.snapshot()["items"],[])
                rates.assert_not_called()


if __name__ == "__main__":
    unittest.main()
