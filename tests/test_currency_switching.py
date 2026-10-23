"""Post-load comparisons use the production cache/batch/analysis path."""
import io
import json
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from steam_price_polisher.batching import BatchPolicy, SteamBatchProvider
from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.models import ExchangeRate, RegionalPriceResult, StorePrice, WishlistItem, WishlistResult
from steam_price_polisher.web_app import BusyError, JobManager, WebApplication
from tests.batch_fixtures import BatchHttpFixture


class CurrencySwitchingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.manager = JobManager(self.path, start_worker=False, batch_policy=BatchPolicy(price_size=1))
        self.app = WebApplication(self.manager)
        self.http = BatchHttpFixture(self.price)
        self.steam = self.enterContext(patch("steam_price_polisher.web_app.SteamClient")).return_value
        self.steam.get_wishlist.return_value = WishlistResult(
            (WishlistItem("20", "Zulu", priority=1), WishlistItem("10", "Alpha", priority=2)), "mock")
        nbp = self.enterContext(patch("steam_price_polisher.web_app.NbpExchangeRateProvider")).return_value
        values = {"USD": 4, "EUR": 5, "GBP": 6, "NOK": .4}
        nbp.get_rate_details.side_effect = lambda currencies: {
            code: ExchangeRate(code, values[code], "2026-10-19") for code in currencies}
        self.enterContext(patch("steam_price_polisher.web_app.SteamBatchProvider",
            side_effect=lambda http, **kwargs: SteamBatchProvider(self.http, **kwargs)))

    @staticmethod
    def price(app_id, region, currency):
        return RegionalPriceResult.available(
            StorePrice(region, currency, 40 if region == "pl" else 10, 40 if region == "pl" else 10, 0),
            ("Zulu" if app_id == "20" else "Alpha") if region != "gb" else ("A" if app_id == "20" else "Z"))

    def execute(self, job):
        queued = self.manager.queue.get_nowait()
        self.assertIs(queued, job)
        self.manager.execute(job)
        self.manager.queue.task_done()
        self.assertIn(job.data["state"], {"complete", "partial"}, job.snapshot())
        return job

    def initial(self, **kwargs):
        return self.execute(self.manager.submit("76561198000000000",
            ComparisonConfig.from_regions(["us"]), "initial", **kwargs))

    def change(self, source, home="pl", regions=("us",), owner="switch"):
        return self.manager.change_currencies(source,
            ComparisonConfig.from_regions(list(regions), home=home), owner)

    def request(self, job, payload, token=None, **overrides):
        raw = json.dumps(payload).encode()
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": f"/api/jobs/{job.id}/currencies",
               "HTTP_HOST": "127.0.0.1:8765", "HTTP_ORIGIN": "http://127.0.0.1:8765",
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw), "HTTP_AUTHORIZATION": "Bearer " + (job.token if token is None else token),
               "REMOTE_ADDR": "switch", **overrides}
        result = {}
        def respond(status, headers):
            result["status"] = int(status.split()[0])
        result["body"] = json.loads(b"".join(self.app(env, respond)))
        return result

    def countries(self, calls):
        output = []
        for url in calls:
            query = parse_qs(urlsplit(url).query)
            output.append(json.loads(query["input_json"][0])["context"]["country_code"].lower()
                          if "input_json" in query else query["cc"][0])
        return output

    def test_baseline_swap_reuses_both_offer_sets_without_discovery_or_http(self):
        source = self.initial()
        before = deepcopy(source.snapshot())
        calls = len(self.http.calls)
        self.assertEqual(set(self.countries(self.http.calls)), {"pl", "us"})
        changed = self.execute(self.change(source, home="us", regions=("pl",)))
        self.assertEqual(len(self.http.calls), calls)
        self.steam.get_wishlist.assert_called_once()
        self.assertEqual(source.snapshot(), before)
        self.assertEqual(changed.data["profile"], before["profile"])
        self.assertEqual(changed.data["previous_job_id"], source.id)
        self.assertEqual([row["app_id"] for row in changed.data["items"]], ["20", "10"])
        for row in changed.data["items"]:
            self.assertIsNotNone(row["comparison"])
            self.assertIsNotNone(row["best_offer_comparison"])
            self.assertEqual(row["live_requests"], 0)
            self.assertEqual(row["comparison"]["home_price"]["currency"], "USD")

    def test_removed_title_stays_out_of_currency_updates_and_shared_cache_survives(self):
        source = self.initial()
        calls = len(self.http.calls)
        source.remove_titles(["20"])
        changed = self.execute(self.change(source, home="us", regions=("pl",)))
        self.assertEqual([row["app_id"] for row in changed.data["items"]], ["10"])
        self.assertEqual(len(self.http.calls), calls)
        fresh = self.initial()
        self.assertEqual([row["app_id"] for row in fresh.data["items"]], ["20", "10"])
        self.assertEqual(len(self.http.calls), calls)

    def test_removing_all_titles_creates_an_empty_currency_update_without_requests(self):
        source = self.initial()
        source.remove_titles(["20", "10"])
        calls = len(self.http.calls)
        changed = self.execute(self.change(source))
        self.assertEqual(changed.data["items"], [])
        self.assertEqual(changed.data["total"], 0)
        self.assertEqual(changed.data["rates"], [])
        self.assertEqual(len(self.http.calls), calls)

    def test_new_storefront_only_and_switch_back_reuses_retained_countries_across_windows(self):
        source = self.initial()
        calls = len(self.http.calls)
        changed = self.execute(self.change(source, regions=("gb",)))
        self.assertEqual(self.countries(self.http.calls[calls:]), ["gb"] * 4)
        calls = len(self.http.calls)
        returned = self.execute(self.change(changed, home="us", regions=("pl",), owner="return"))
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(len(returned.data["items"]), 2)
        self.steam.get_wishlist.assert_called_once()

    def test_name_order_is_frozen_when_new_baseline_has_different_names(self):
        source = self.initial(order="name")
        self.assertEqual([row["app_id"] for row in source.data["items"]], ["10", "20"])
        changed = self.execute(self.change(source, home="gb", regions=("us",)))
        self.assertEqual([row["app_id"] for row in changed.data["items"]], ["10", "20"])
        self.assertEqual(changed.data["order"], "name")

    def test_observations_survive_an_uncompared_original_game(self):
        self.http.price = lambda app, region, currency: (
            RegionalPriceResult.no_regional_price("Unavailable") if region == "pl"
            else self.price(app, region, currency))
        source = self.initial()
        self.assertTrue(all(row["comparison"] is None for row in source.data["items"]))
        calls = len(self.http.calls)
        changed = self.execute(self.change(source, home="us", regions=("gb",)))
        self.assertTrue(all(row["comparison"] is not None for row in changed.data["items"]))
        self.assertEqual(set(self.countries(self.http.calls[calls:])), {"gb"})

    def test_expired_offers_refresh_without_refreshing_fresh_default_prices(self):
        source = self.initial()
        with closing(sqlite3.connect(self.path / "cache.sqlite3")) as connection:
            with connection:
                connection.execute("UPDATE batch_observations SET fetched_at=fetched_at-901 WHERE kind='offer' AND region='us'")
        calls = len(self.http.calls)
        self.execute(self.change(source, home="us", regions=("pl",)))
        new_calls = self.http.calls[calls:]
        self.assertEqual(len(new_calls), 2)
        self.assertEqual(self.countries(new_calls), ["us", "us"])
        self.assertTrue(all("GetItems" in url for url in new_calls))

    def test_endpoint_auth_validation_and_active_lineage_lock(self):
        source = self.initial()
        for payload in ({}, [], {"regions": []}, {"regions": ["pl"]},
                        {"regions": ["us"], "app_ids": ["99"]}, {"regions": ["us"], "order": "name"}):
            self.assertEqual(self.request(source, payload)["status"], 400)
        self.assertEqual(self.request(source, {"regions": ["us"]}, token="invalid")["status"], 404)
        self.assertEqual(self.request(source, {"regions": ["us"]}, HTTP_ORIGIN="https://evil.test")["status"], 403)
        response = self.request(source, {"home": "us", "regions": ["pl"]})
        self.assertEqual(response["status"], 202)
        changed = self.manager.jobs[response["body"]["id"]]
        self.assertNotEqual(changed.token, source.token)
        self.assertIsNone(self.manager.get(changed.id, source.token))
        with self.assertRaises(BusyError):
            self.change(source, owner="different-connection")
        self.execute(changed)

    def test_unfinished_and_expired_sources_are_rejected(self):
        source = self.manager.submit("example", ComparisonConfig(), "initial")
        self.assertEqual(self.request(source, {"regions": ["us"]})["status"], 429)
        self.execute(source)
        source.updated -= 3601
        self.assertEqual(self.request(source, {"regions": ["us"]})["status"], 404)

    def test_cancellation_and_failure_leave_original_comparison_intact(self):
        source = self.initial()
        before = deepcopy(source.snapshot())
        changed = self.change(source, regions=("gb",))
        self.manager.cancel_job(changed)
        self.manager.queue.get_nowait()
        self.manager.execute(changed)
        self.manager.queue.task_done()
        self.assertEqual(changed.data["state"], "cancelled")
        self.assertEqual(source.snapshot(), before)
        retry = self.change(source, regions=("gb",), owner="retry")
        self.manager.queue.get_nowait()
        with patch.object(self.manager, "runner", side_effect=RuntimeError("private path")):
            self.manager.execute(retry)
        self.manager.queue.task_done()
        self.assertEqual(retry.data["state"], "failed")
        self.assertNotIn("private path", str(retry.snapshot()))
        self.assertEqual(source.snapshot(), before)

    def test_featured_catalog_selection_membership_and_pagination_are_preserved(self):
        source = self.initial(creator_request={"mode": "featured"})
        before = deepcopy(source.snapshot())
        calls = len(self.http.calls)
        changed = self.execute(self.change(source, home="us", regions=("pl",)))
        self.assertEqual(changed.data["catalogs"], before["catalogs"])
        self.assertEqual([(row["app_id"], row["creator_ids"]) for row in changed.data["items"]],
                         [(row["app_id"], row["creator_ids"]) for row in before["items"]])
        self.assertEqual(len(self.http.calls), calls)
        self.steam.get_wishlist.assert_not_called()

    def test_catalog_page_is_not_rediscovered_when_baseline_changes(self):
        from steam_price_polisher.creators import CREATORS
        creator_id = next(iter(CREATORS))
        page = {"products": [{"app_id": "20", "name": "Zulu"}, {"app_id": "10", "name": "Alpha"}],
                "total": 100, "next_start": 25, "has_more": True, "source": "live"}
        with patch.object(self.manager.catalogs, "get_page", return_value=page) as discover:
            source = self.initial(creator_request={"mode": "catalog", "creator_id": creator_id, "start": 0})
            changed = self.execute(self.change(source, home="gb", regions=("us",)))
        discover.assert_called_once()
        self.assertEqual(changed.data["catalogs"], source.data["catalogs"])
        self.assertEqual(changed.data["catalogs"][creator_id]["next_start"], 25)

    def test_empty_catalog_changes_need_no_rates_or_price_requests(self):
        from steam_price_polisher.creators import CREATORS
        creator_id = next(iter(CREATORS))
        with patch.object(self.manager.catalogs, "get_page",
                          return_value={"products": [], "total": 0, "next_start": 0, "has_more": False, "source": "live"}):
            source = self.initial(creator_request={"mode": "catalog", "creator_id": creator_id, "start": 0})
        changed = self.execute(self.change(source, home="gb", regions=("us",)))
        self.assertEqual(changed.data["items"], [])
        self.assertEqual(changed.data["rates"], [])
        self.assertEqual(self.http.calls, [])

    def test_currency_changes_keep_owner_and_capacity_limits(self):
        source = self.initial()
        self.manager.max_jobs = 1
        with self.assertRaises(BusyError):
            self.change(source)
        self.manager.max_jobs = 20
        self.manager.submit("example", ComparisonConfig(), "switch")
        with self.assertRaises(BusyError):
            self.change(source)

    def test_partial_completion_can_be_recompared(self):
        from steam_price_polisher.steam_access import SteamTemporaryError
        original_price = self.http.price
        def fail_home(app, region, currency):
            if region == "pl":
                raise SteamTemporaryError("Unavailable", app_id=app, region=region)
            return original_price(app, region, currency)
        self.http.price = fail_home
        source = self.initial()
        self.assertEqual(source.data["state"], "partial")
        self.http.price = original_price
        changed = self.execute(self.change(source, home="us", regions=("gb",)))
        self.assertEqual(changed.data["state"], "complete")
        self.steam.get_wishlist.assert_called_once()

    def test_cancellation_after_one_window_retains_both_offers_for_retry(self):
        source = self.initial()
        before = deepcopy(source.snapshot())
        changed = self.change(source, regions=("gb",))
        append = changed.append
        def cancel_after_row(item):
            append(item)
            self.manager.cancel_job(changed)
        self.manager.queue.get_nowait()
        with patch.object(changed, "append", side_effect=cancel_after_row):
            self.manager.execute(changed)
        self.manager.queue.task_done()
        self.assertEqual(changed.data["state"], "cancelled")
        self.assertEqual(len(changed.data["items"]), 1)
        self.assertEqual(source.snapshot(), before)
        calls = len(self.http.calls)
        retry = self.execute(self.change(source, regions=("gb",), owner="retry"))
        self.assertEqual(self.countries(self.http.calls[calls:]), ["gb", "gb"])
        self.assertEqual(retry.data["items"][0]["live_requests"], 0)
        self.assertTrue(all(row["best_offer_comparison"] is not None for row in retry.data["items"]))
        self.steam.get_wishlist.assert_called_once()

    def test_network_denial_stops_currency_retrieval_and_preserves_original(self):
        from steam_price_polisher.http_client import HttpClientError
        source = self.initial()
        before = deepcopy(source.snapshot())
        changed = self.change(source, regions=("gb",))
        self.manager.queue.get_nowait()
        with patch.object(self.http, "get_json", side_effect=HttpClientError("private details", network_access_denied=True)) as fetch:
            self.manager.execute(changed)
        self.manager.queue.task_done()
        fetch.assert_called_once()
        self.assertEqual(changed.data["state"], "failed")
        self.assertEqual(changed.data["error_code"], "network_access_denied")
        self.assertEqual(source.snapshot(), before)
        self.assertNotIn("private details", str(changed.snapshot()))

    def test_library_currency_endpoint_stays_behind_feature_flag(self):
        self.steam.get_owned_library.return_value = self.steam.get_wishlist.return_value
        source = self.initial(library=True)
        self.assertEqual(self.request(source, {"regions": ["us"]})["status"], 404)
        self.app = WebApplication(self.manager, owned_library_enabled=True)
        response = self.request(source, {"home": "us", "regions": ["pl"]})
        self.assertEqual(response["status"], 202)
        self.execute(self.manager.jobs[response["body"]["id"]])
        self.steam.get_owned_library.assert_called_once()
        self.steam.get_wishlist.assert_not_called()
