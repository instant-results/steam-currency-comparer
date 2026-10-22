from tests.batch_fixtures import mock_batch_prices
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.models import ExchangeRate, WishlistItem, WishlistResult, StorePrice, RegionalPriceResult, PriceStatus
from steam_price_polisher.web_app import WebApplication, JobManager, validate_request, InputError, BusyError
from tests.test_exchange_rates import table_payload

PROFILE = "76561198000000000"


class WebAppTests(unittest.TestCase):
    def test_real_http_denial_reaches_job_api_for_wishlist_vanity_rates_and_prices(self):
        import errno
        import urllib.error
        from steam_price_polisher.http_client import UrllibJsonHttpClient

        # Exercise the real HTTP, retry, Steam and rate adapters, not a mocked failure enum.
        for stage in ("wishlist", "vanity", "rates", "prices", "name_prefetch"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                manager = JobManager(directory, start_worker=False, api_key="secret")
                manager.gate = Mock()
                identifier = "https://steamcommunity.com/id/example" if stage == "vanity" else PROFILE
                job = manager.submit(identifier, ComparisonConfig(), "test",
                                     order="name" if stage == "name_prefetch" else "priority")
                raw_client = UrllibJsonHttpClient()
                denial = urllib.error.URLError(PermissionError(errno.EACCES, "private path"))
                def respond(request, **kwargs):
                    url = request.full_url
                    if stage in {"wishlist", "vanity"} or (stage == "rates" and "api.nbp.pl" in url) or "appdetails" in url or "/GetItems/" in url:
                        raise denial
                    if "GetWishlist" in url:
                        payload = {"response": {"items": [{"appid": 10}, {"appid": 20}]}}
                    else:
                        payload = (table_payload("B", "2026-09-02", AED=1) if "/tables/b/" in url
                                   else table_payload("A", "2026-09-08", USD=4, EUR=4))
                    response = Mock()
                    response.__enter__ = Mock(return_value=response)
                    response.__exit__ = Mock(return_value=False)
                    response.read.return_value = json.dumps(payload).encode()
                    return response
                with patch.object(raw_client._opener, "open", side_effect=respond) as requests, patch(
                    "steam_price_polisher.web_app.UrllibJsonHttpClient", return_value=raw_client
                ):
                    manager.execute(job)
                self.app = WebApplication(manager)
                result = self.request("/api/jobs/" + job.id, token=job.token)["json"]
                self.assertEqual(result["state"], "failed")
                self.assertEqual(result["error_code"], "network_access_denied")
                self.assertIn("local permissions", result["error"])
                self.assertNotIn("secret", json.dumps(result))
                self.assertNotIn("private path", json.dumps(result))
                self.assertEqual(requests.call_count, {"wishlist": 1, "vanity": 1, "rates": 2, "prices": 4, "name_prefetch": 4}[stage])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.manager = JobManager(self.directory.name, start_worker=False)
        self.app = WebApplication(self.manager)

    def request(self, path, method="GET", body=None, token="", **headers):
        raw = json.dumps(body).encode() if body is not None else b""
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "HTTP_HOST": "127.0.0.1:8765",
               "HTTP_ORIGIN": "http://127.0.0.1:8765", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
               "HTTP_AUTHORIZATION": "Bearer " + token, "REMOTE_ADDR": "127.0.0.1", **headers}
        result = {}
        def respond(status, response_headers):
            result["status"] = int(status.split()[0]); result["headers"] = dict(response_headers)
        result["body"] = b"".join(self.app(env, respond))
        if result["headers"]["Content-Type"].startswith("application/json"):
            result["json"] = json.loads(result["body"])
        return result

    def submit(self):
        response = self.request("/api/jobs", "POST", {"identifier": PROFILE, "regions": ["us", "de"]})
        self.assertEqual(response["status"], 202)
        return response["json"]

    def test_assets_are_allowlisted_and_security_headers_apply(self):
        for asset in ["/", "/app.js", "/library.js", "/app.css", "/favicon.svg"]:
            with self.subTest(asset=asset):
                response = self.request(asset)
                self.assertEqual(response["status"], 200)
                self.assertIn("frame-ancestors 'none'", response["headers"]["Content-Security-Policy"])
        for path in ["/.env", "/PROJECT_CONTEXT.md", "/../steam_price_polisher/cache.py", "/.steam-price-polisher/cache.sqlite3"]:
            self.assertEqual(self.request(path)["status"], 404)
        self.assertEqual(self.request("/", HTTP_HOST="evil.test")["status"], 400)

    def test_currency_flag_assets_cover_picker_currencies_and_remain_allowlisted(self):
        import re
        import xml.etree.ElementTree as ET
        from steam_price_polisher.configuration import STOREFRONTS

        response = self.request("/flags.svg")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "image/svg+xml")
        sprite = ET.fromstring(response["body"])
        self.assertEqual(sprite.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual({symbol.attrib["id"] for symbol in sprite},
                         {"eu" if value["currency"] == "EUR" else region
                          for region, value in STOREFRONTS.items()})
        identifiers = [element.attrib["id"] for element in sprite.iter() if "id" in element.attrib]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for reference in re.findall(rb"url\(#([^)]+)\)", response["body"]):
            self.assertIn(reference.decode(), identifiers)
        self.assertIn("default-src 'self'", response["headers"]["Content-Security-Policy"])
        head = self.request("/flags.svg", method="HEAD")
        self.assertEqual(head["status"], 200)
        self.assertEqual(head["body"], b"")
        self.assertEqual(self.request("/flags.svg", method="POST", body={})["status"], 404)
        for path in ("/flags/zz.svg", "/flags/eu.svg", "/flags/README.md",
                     "/flags/LICENSE.md", "/flags/../app.js", "/flags/../../.env"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"], 404)

    def test_release_version_is_consistent_in_page_and_health(self):
        from steam_price_polisher.version import __version__

        page = self.request("/")["body"].decode()
        self.assertIn(f"v{__version__}", page)
        self.assertNotIn("{{APP_VERSION}}", page)
        self.assertNotIn("{{OWNED_LIBRARY_ENABLED}}", page)
        self.assertEqual(self.request("/api/health")["json"],
                         {"status": "ok", "version": __version__})

    def test_owned_library_flag_controls_page_and_submission_without_initializing_jobs(self):
        from steam_price_polisher.web_app import OWNED_LIBRARY_ENABLED
        self.assertFalse(OWNED_LIBRARY_ENABLED)
        page = self.request("/")["body"].decode()
        self.assertIn('data-owned-library-enabled="false"', page)
        self.assertIn('<button id="library-tab" hidden', page)
        response = self.request("/api/library-jobs", "POST", {"identifier":PROFILE,"regions":["us"]})
        self.assertEqual(response["status"],404)
        self.assertEqual(len(self.manager.jobs),0)
        self.app = WebApplication(self.manager, owned_library_enabled=True)
        page = self.request("/")["body"].decode()
        self.assertIn('data-owned-library-enabled="true"',page)
        self.assertNotIn('<button id="library-tab" hidden',page)
        response = self.request("/api/library-jobs", "POST", {"identifier":PROFILE,"regions":["us"]})
        self.assertEqual(response["status"],202)

    def test_library_controls_follow_wishlist_and_have_unique_accessible_ids(self):
        from html.parser import HTMLParser
        class PageControls(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids = []; self.library_filters = []; self.references = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if "id" in attrs: self.ids.append(attrs["id"])
                if "library-filter" in attrs.get("class", "").split(): self.library_filters.append(tag)
                for key in ("for", "aria-controls", "aria-labelledby", "aria-describedby"):
                    if key in attrs: self.references.extend(attrs[key].split())
        page = self.request("/")["body"].decode()
        parser = PageControls(); parser.feed(page)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertEqual(parser.library_filters, ["button"] * 5)
        self.assertTrue(set(parser.references) <= set(parser.ids))
        self.assertLess(page.index('id="wishlist-tab"'), page.index('id="library-tab"'))
        self.assertLess(page.index('id="library-tab"'), page.index('id="developers-tab"'))

    def test_job_requires_capability_token_and_can_be_cancelled(self):
        job = self.submit(); path = "/api/jobs/" + job["id"]
        self.assertEqual(self.request(path)["status"], 404)
        self.assertEqual(self.request(path, token="incorrect")["status"], 404)
        self.assertEqual(self.request(path, token="żółć")["status"], 404)
        response = self.request(path, token=job["token"])
        self.assertEqual(response["json"]["state"], "queued")
        self.assertEqual(response["json"]["profile"], PROFILE)
        self.assertEqual(response["json"]["regions"], ["us", "de"])
        self.assertEqual(response["json"]["order"], "priority")
        self.assertNotIn(job["token"], response["body"].decode())
        self.assertEqual(self.request(path + "/cancel", "POST", {}, job["token"])["json"]["state"], "cancelling")
        self.manager.execute(self.manager.jobs[job["id"]])
        self.assertEqual(self.request(path, token=job["token"])["json"]["state"], "cancelled")

    def test_cross_origin_and_invalid_bodies_do_not_create_jobs(self):
        for overrides in [{"HTTP_ORIGIN": "https://evil.test"}, {"HTTP_ORIGIN": ""}, {"CONTENT_TYPE": "text/plain"}, {"CONTENT_LENGTH": "99999"}]:
            self.assertIn(self.request("/api/jobs", "POST", {"identifier": PROFILE, "regions": ["de"]}, **overrides)["status"], {400, 403})
        self.assertEqual(len(self.manager.jobs), 0)

    def test_validates_profile_hosts_regions_and_disallows_credentials(self):
        for identifier in [PROFILE, "https://steamcommunity.com/profiles/" + PROFILE, "https://steamcommunity.com/id/example", "https://store.steampowered.com/wishlist/profiles/" + PROFILE]:
            validate_request({"identifier": identifier, "regions": ["de"]})
        for identifier in ["https://evil.test/steamcommunity.com/id/example", "http://localhost/", "file:///etc/passwd", "123", "https://steamcommunity.com/id/a?key=secret", "https://steamcommunity.com:443/id/example", "https://steamcommunity.com/id/../"]:
            with self.subTest(identifier=identifier), self.assertRaises(InputError):
                validate_request({"identifier": identifier, "regions": ["de"]})
        for body in [{"identifier": PROFILE, "regions": []}, {"identifier": PROFILE, "regions": ["us", "us"]}, {"identifier": PROFILE, "regions": ["de"], "order": "random"}, {"identifier": PROFILE, "regions": ["de"], "cookie": "secret"}]:
            self.assertEqual(self.request("/api/jobs", "POST", body)["status"], 400)

    def test_accepts_and_retains_each_wishlist_order(self):
        for index, order in enumerate(("priority", "date_added", "name")):
            response = self.request(
                "/api/jobs",
                "POST",
                {"identifier": PROFILE, "regions": ["de"], "order": order},
                REMOTE_ADDR=f"order-{index}",
            )
            self.assertEqual(response["status"], 202)
            stored = self.manager.jobs[response["json"]["id"]]
            self.assertEqual(stored.order, order)
            self.assertEqual(stored.snapshot()["order"], order)

    def test_duplicate_and_excess_jobs_are_bounded(self):
        self.submit()
        with self.assertRaises(BusyError):
            self.manager.submit(PROFILE, ComparisonConfig(), "127.0.0.1")
        self.manager.max_jobs = 1
        with self.assertRaises(BusyError):
            self.manager.submit(PROFILE, ComparisonConfig(), "other")

    def test_expired_job_is_inaccessible(self):
        job = self.submit(); stored = self.manager.jobs[job["id"]]
        stored.update(state="complete"); stored.updated -= 3601
        self.assertEqual(self.request("/api/jobs/" + job["id"], token=job["token"])["status"], 404)

    def test_worker_failure_is_redacted(self):
        job = self.submit(); stored = self.manager.jobs[job["id"]]
        self.manager.runner = Mock(side_effect=RuntimeError("secret-key local-path"))
        self.manager.execute(stored)
        self.assertEqual(stored.snapshot()["state"], "failed")
        self.assertNotIn("secret-key", str(stored.snapshot()))
        self.assertEqual(stored.identifier, "")

    def test_local_file_permission_error_is_not_reported_as_network_denial(self):
        import errno
        created = self.submit()
        stored = self.manager.jobs[created["id"]]
        self.manager.runner = Mock(side_effect=PermissionError(errno.EACCES, "private cache path"))
        self.manager.execute(stored)
        self.assertEqual(stored.snapshot()["state"], "failed")
        self.assertNotEqual(stored.snapshot().get("error_code"), "network_access_denied")
        self.assertNotIn("private cache path", str(stored.snapshot()))

    def test_analysis_integrates_prices_rates_and_cache_resume(self):
        job = self.submit(); stored = self.manager.jobs[job["id"]]
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp, mock_batch_prices(steam.return_value.get_regional_price):
            steam.return_value.get_wishlist.return_value = WishlistResult((WishlistItem("10", "Test Game"),), "mock")
            nbp.return_value.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4, "2026-09-08"), "EUR": ExchangeRate("EUR", 4.3, "2026-09-08")}
            steam.return_value.get_regional_price.side_effect = lambda app, region, currency: RegionalPriceResult(
                status=PriceStatus.AVAILABLE, price=StorePrice(region, currency, 40 if region == "pl" else 12, 40 if region == "pl" else 12, 0),
                game_name="Test Game", developers=("Developer",), publishers=("Publisher",))
            self.manager.execute(stored)
            result = stored.snapshot()
            self.assertEqual(result["state"], "complete")
            self.assertTrue(result["items"][0]["comparison"]["is_fair"])
            self.assertEqual(result["rates"][0]["effective_date"], "2026-09-08")
            self.assertEqual(result["items"][0]["source_summary"], "live 6")
            self.assertNotIn("wishlist_file", steam.call_args.kwargs)
            second = self.manager.submit(PROFILE, ComparisonConfig(), "other")
            self.manager.execute(second)
            self.assertEqual(second.snapshot()["items"][0]["source_summary"], "cache 3")
            self.assertEqual(steam.return_value.get_regional_price.call_count, 3)

    def test_wishlist_refreshes_old_price_cache_for_credits_then_reuses_it(self):
        from steam_price_polisher.cache import SQLiteCache

        cache = SQLiteCache(Path(self.directory.name) / "cache.sqlite3")
        for region, currency in (("pl", "PLN"), ("us", "USD"), ("de", "EUR")):
            cache.put_price("10", region, currency, RegionalPriceResult.available(
                StorePrice(region, currency, 12, 12, 0), "Old Game"))
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp, mock_batch_prices(steam.return_value.get_regional_price):
            steam.return_value.get_wishlist.return_value = WishlistResult((WishlistItem("10"),), "mock")
            nbp.return_value.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4, "2026-09-08"), "EUR": ExchangeRate("EUR", 4.3, "2026-09-08")}
            steam.return_value.get_regional_price.side_effect = lambda app, region, currency: RegionalPriceResult(
                PriceStatus.AVAILABLE, StorePrice(region, currency, 15, 15, 0), "Updated Game",
                developers=("First developer", "Second developer"), publishers=("Publisher",))
            first = self.manager.submit(PROFILE, ComparisonConfig(), "first")
            self.manager.execute(first)
            first_item = first.snapshot()["items"][0]
            self.assertEqual(first_item["developers"], ("First developer", "Second developer"))
            self.assertEqual(first_item["publishers"], ("Publisher",))
            self.assertEqual(first_item["comparison"]["home_price"]["amount"], 12)
            self.assertEqual(first_item["source_summary"], "cache 3, live 3")
            second = self.manager.submit(PROFILE, ComparisonConfig(), "second")
            self.manager.execute(second)
            self.assertEqual(second.snapshot()["items"][0]["developers"], first_item["developers"])
            self.assertEqual(second.snapshot()["items"][0]["source_summary"], "cache 3")
            self.assertEqual(steam.return_value.get_regional_price.call_count, 3)

    def test_partial_results_hide_upstream_error_details(self):
        from steam_price_polisher.steam_access import SteamTemporaryError
        job = self.submit(); stored = self.manager.jobs[job["id"]]
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp, mock_batch_prices(steam.return_value.get_regional_price):
            steam.return_value.get_wishlist.return_value = WishlistResult((WishlistItem("10"),), "mock")
            nbp.return_value.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4, "2026-09-08"), "EUR": ExchangeRate("EUR", 4.3, "2026-09-08")}
            steam.return_value.get_regional_price.side_effect = SteamTemporaryError("secret", app_id="10", region="pl")
            self.manager.execute(stored)
        self.assertEqual(stored.snapshot()["state"], "partial")
        self.assertNotIn("secret", json.dumps(stored.snapshot()))

    def test_tls_error_does_not_blame_profile_privacy(self):
        from steam_price_polisher.models import WishlistFailure
        created = self.submit()
        stored = self.manager.jobs[created["id"]]
        with patch("steam_price_polisher.web_app.SteamClient") as steam:
            steam.return_value.get_wishlist.return_value = WishlistResult((), "failed", failure=WishlistFailure.TLS)
            self.manager.execute(stored)
        self.assertEqual(stored.snapshot()["state"], "failed")
        self.assertIn("server connection problem", stored.snapshot()["error"])
        self.assertNotIn("No public wishlist games", stored.snapshot()["error"])

    def test_755_game_wishlist_passes_size_validation(self):
        created = self.submit()
        stored = self.manager.jobs[created["id"]]
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.CachedExchangeRateProvider") as rates, patch("steam_price_polisher.web_app.AnalysisRunner") as runner:
            steam.return_value.get_wishlist.return_value = WishlistResult(tuple(WishlistItem(str(i + 1)) for i in range(755)), "mock")
            rates.return_value.get_rate_details.return_value = {"PLN": ExchangeRate("PLN", 1, None), "USD": ExchangeRate("USD", 4, "2026-09-08")}
            runner.return_value.run.return_value = iter(())
            self.manager.execute(stored)
        self.assertEqual(stored.snapshot()["total"], 755)
        self.assertEqual(stored.snapshot()["state"], "complete")
        runner.return_value.run.assert_called_once()
        self.assertEqual(runner.return_value.run.call_args.kwargs["order"], "priority")

    def test_non_pln_baseline_converts_both_legs_and_preserves_rate_dates(self):
        _, config = validate_request({"identifier": PROFILE, "home": "gb", "regions": ["no", "pl"]})
        stored = self.manager.submit(PROFILE, config, "test-gbp")
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp, mock_batch_prices(steam.return_value.get_regional_price):
            steam.return_value.get_wishlist.return_value = WishlistResult((WishlistItem("10"),), "mock")
            nbp.return_value.get_rate_details.return_value = {"NOK": ExchangeRate("NOK", .4, "2026-09-08"), "GBP": ExchangeRate("GBP", 5, "2026-09-09")}
            steam.return_value.get_regional_price.side_effect = lambda app, region, currency: RegionalPriceResult.available(StorePrice(region, currency, {"gb":10,"no":100,"pl":60}[region]), "Game")
            self.manager.execute(stored)
        result = stored.snapshot()
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["home"], "gb")
        comparison = result["items"][0]["comparison"]
        self.assertEqual(comparison["home_price"]["currency"], "GBP")
        self.assertEqual([price["amount_in_home"] for price in comparison["alternatives"]], [8,12])
        self.assertFalse(comparison["is_fair"])
        for rate in result["rates"]:
            if rate["currency"] != "PLN":
                self.assertIsNotNone(rate["retrieved_at_utc"])
        self.assertEqual({rate["effective_date"] for rate in result["rates"]}, {None,"2026-09-08","2026-09-09"})

    def test_existing_baselines_accept_more_alternatives_and_reject_home(self):
        from itertools import combinations
        regions = ["pl", "us", "de", "no", "gb"]
        for home in regions:
            for alternatives in combinations([region for region in regions if region != home], 2):
                _, config = validate_request({"identifier": PROFILE, "home": home, "regions": list(alternatives)})
                self.assertEqual(config.home.region, home)
            with self.assertRaises(ValueError):
                validate_request({"identifier": PROFILE, "home": home, "regions": [home]})
            _, config = validate_request({"identifier": PROFILE, "home": home, "regions": [r for r in regions if r != home]})
            self.assertEqual(len(config.alternatives), 4)

    def test_example_mode_loads_curated_wishlist_including_witcher_3(self):
        from steam_price_polisher.web_app import EXAMPLE_WISHLIST
        identifier, config = validate_request({"identifier": "example", "regions": ["us", "de"]})
        self.assertEqual(identifier, "example")
        self.assertEqual(len(EXAMPLE_WISHLIST), 7)
        app_ids = {item.app_id for item in EXAMPLE_WISHLIST}
        self.assertIn("292030", app_ids)
        self.assertIn("413150", app_ids)
        self.assertIn("1091500", app_ids)
        self.assertIn("1245620", app_ids)

        stored = self.manager.submit("example", config, "test-example")
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp, mock_batch_prices(steam.return_value.get_regional_price):
            nbp.return_value.get_rate_details.return_value = {"USD": ExchangeRate("USD", 4, "2026-09-08"), "EUR": ExchangeRate("EUR", 4.3, "2026-09-08")}
            steam.return_value.get_regional_price.side_effect = lambda app, region, currency: RegionalPriceResult.available(StorePrice(region, currency, 50, 50, 0), "Game " + app)
            self.manager.execute(stored)
            steam.return_value.get_wishlist.assert_not_called()
            snapshot = stored.snapshot()
            self.assertEqual(snapshot["state"], "complete")
            self.assertEqual(snapshot["total"], 7)
            self.assertEqual(len(snapshot["items"]), 7)
            returned_ids = [item["app_id"] for item in snapshot["items"]]
            self.assertIn("292030", returned_ids)

    def test_background_worker_processes_submitted_job(self):
        finished = threading.Event()
        def work(job):
            job.update(state="complete"); finished.set()
        manager = JobManager(self.directory.name, runner=work)
        job = manager.submit(PROFILE, ComparisonConfig(), "test")
        self.assertTrue(finished.wait(2))
        self.assertEqual(job.snapshot()["state"], "complete")


if __name__ == "__main__":
    unittest.main()
