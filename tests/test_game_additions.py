"""Game discovery, explicit selections and independent work/result capacity."""
import io
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from steam_price_polisher.games import GameSearch
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.web_app import JobManager, WebApplication, validate_request, BusyError
from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.models import ExchangeRate, RegionalPriceResult, StorePrice
from tests.batch_fixtures import mock_batch_prices


class GameDiscoveryTests(unittest.TestCase):
    def test_search_cache_expires_and_remains_bounded(self):
        clock = Mock(return_value=0)
        client = Mock(get_json=Mock(return_value={"response": {"metadata": {"count": 0}}}))
        search = GameSearch(clock)
        search.search(client, "game", "pl")
        clock.return_value = 601
        search.search(client, "game", "pl")
        self.assertEqual(client.get_json.call_count, 2)
        for index in range(130):
            search.search(client, f"game {index}", "pl")
        self.assertEqual(len(search.cache), 128)

    def test_search_filters_non_apps_deduplicates_and_caches_by_country(self):
        client = Mock()
        good = {"item_type": 0, "id": 10, "success": 1, "type": 0, "name": "A <game>"}
        client.get_json.return_value = {"response": {"metadata": {}, "store_items": [good, good,
            {**good, "item_type": 1}, {**good, "id": True}, {**good, "success": 15}]}}
        search = GameSearch(lambda: 10)
        first = search.search(client, "game", "pl")
        self.assertEqual(first["games"], [{"app_id": "10", "name": "A <game>", "kind": "Game"}])
        self.assertEqual(search.search(client, "GAME", "pl"), first)
        self.assertEqual(client.get_json.call_count, 1)
        search.search(client, "game", "us")
        self.assertEqual(client.get_json.call_count, 2)

    def test_empty_search_is_distinct_from_malformed_search(self):
        client = Mock(get_json=Mock(return_value={"response": {"metadata": {"count": 0}}}))
        self.assertEqual(GameSearch(lambda: 0).search(client, "no-match", "pl"), {"games": []})
        for value in ({}, {"response": []}, {"response": {"metadata": {}, "store_items": "bad"}}):
            client.get_json.return_value = value
            with self.assertRaises(HttpClientError): GameSearch(lambda: 0).search(client, "game", "pl")


class GameAdditionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.manager = JobManager(directory.name, start_worker=False)
        self.app = WebApplication(self.manager)

    def request(self, path, body, origin="http://127.0.0.1:8765"):
        raw = json.dumps(body).encode()
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": path, "HTTP_HOST": "127.0.0.1:8765",
               "HTTP_ORIGIN": origin, "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw), "REMOTE_ADDR": "test"}
        output = {}
        def respond(status, headers): output["status"] = int(status.split()[0])
        output["data"] = json.loads(b"".join(self.app(env, respond)))
        return output

    def test_selection_validation(self):
        body = {"identifier": "selection", "home": "pl", "regions": ["us"], "app_ids": ["10"], "added_app_ids": ["10"]}
        validate_request(body)
        for value in ([], ["0"], [True], ["4294967296"], ["10", "10"], ["10"] * 1001):
            with self.assertRaises(ValueError): validate_request({**body, "app_ids": value})
        with self.assertRaises(ValueError): validate_request({**body, "added_app_ids": ["20"]})

    def test_search_route_protects_origin_and_handles_failure(self):
        body = {"query": "Hades", "home": "pl"}
        with patch.object(self.manager.game_search, "search", return_value={"games": []}) as search:
            self.assertEqual(self.request("/api/games/search", body, "https://evil.test")["status"], 403)
            search.assert_not_called()
            self.assertEqual(self.request("/api/games/search", body)["data"], {"games": []})
        with patch.object(self.manager.game_search, "search", side_effect=HttpClientError("private URL")):
            result = self.request("/api/games/search", body)
            self.assertEqual(result["status"], 503)
            self.assertNotIn("private URL", str(result))
        self.assertEqual(self.request("/api/games/search", {**body, "home": []})["status"], 400)

    def test_explicit_selection_skips_discovery_and_retains_manual_origin(self):
        body = {"identifier": "76561198000000000", "regions": ["us"], "app_ids": ["20", "10"], "added_app_ids": ["10"]}
        result = self.request("/api/jobs", body)
        self.assertEqual(result["status"], 202)
        job = self.manager.jobs[result["data"]["id"]]
        self.manager.queue.get_nowait(); self.manager.queue.task_done()
        price = lambda app, region, currency: RegionalPriceResult.available(StorePrice(region, currency, 10), "Game " + app)
        with patch("steam_price_polisher.web_app.SteamClient") as steam, mock_batch_prices(price), patch(
                "steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp:
            nbp.return_value.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4, "2026-10-23")}
            self.manager.execute(job)
            self.assertEqual(job.data["state"], "complete", job.data)
            steam.return_value.get_wishlist.assert_not_called()
        self.assertEqual([row["app_id"] for row in job.data["items"]], ["20", "10"])
        self.assertEqual([row["manually_added"] for row in job.data["items"]], [False, True])
        changed = self.manager.change_currencies(job, ComparisonConfig(), "test")
        self.assertEqual(changed.added_app_ids, ("10",))
        job.remove_titles(["10"])
        self.assertEqual(job.request_app_ids, ("20",))
        self.assertEqual(job.added_app_ids, ())

    def test_completed_jobs_do_not_block_new_work_and_active_jobs_still_do(self):
        self.manager.max_jobs = 1
        for _ in range(25):
            job = self.manager.submit("example", ComparisonConfig(), "test")
            self.manager.queue.get_nowait(); self.manager.queue.task_done()
            job.update(state="complete")
        job = self.manager.submit("example", ComparisonConfig(), "test")
        with self.assertRaises(BusyError): self.manager.submit("example", ComparisonConfig(), "other")

    def test_retention_evicts_old_results_without_evicting_active_work(self):
        self.manager.max_completed_jobs = 2
        for _ in range(5):
            job = self.manager.submit("example", ComparisonConfig(), "test")
            self.manager.queue.get_nowait(); self.manager.queue.task_done()
            job.update(state="complete")
        active = self.manager.submit("example", ComparisonConfig(), "test")
        self.assertEqual(len(self.manager.jobs), 3)
        self.manager.completed_bytes = 1
        with self.manager.lock: self.manager._prune_completed(0)
        self.assertEqual(list(self.manager.jobs), [active.id])
