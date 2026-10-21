"""Supported-market registry, full selections and production cache integration."""
import io
import json
import tempfile
import unittest
from html import unescape
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import re

from steam_price_polisher.configuration import ComparisonConfig, REGION_CURRENCIES, STOREFRONTS
from steam_price_polisher.batching import SteamBatchProvider, parse_offer
from steam_price_polisher.models import ExchangeRate, RegionalPriceResult, StorePrice, WishlistItem, WishlistResult
from steam_price_polisher.web_app import JobManager, WebApplication
from steam_price_polisher.steam_access import SteamClient, SteamRegionMismatchError
from tests.batch_fixtures import BatchHttpFixture


class StorefrontTests(unittest.TestCase):
    def test_one_country_per_live_currency_and_all_baselines(self):
        self.assertEqual(len(STOREFRONTS), 37)
        self.assertEqual(len(set(REGION_CURRENCIES.values())), 37)
        self.assertEqual([country for country, code in REGION_CURRENCIES.items() if code == "USD"], ["us"])
        self.assertEqual([country for country, code in REGION_CURRENCIES.items() if code == "EUR"], ["de"])
        self.assertNotIn("TRY", REGION_CURRENCIES.values())
        for country in STOREFRONTS:
            with self.subTest(home=country):
                others = [value for value in STOREFRONTS if value != country]
                config = ComparisonConfig.from_regions(others, home=country)
                self.assertEqual(len(config.alternatives), 36)
                self.assertEqual([value.region for value in config.alternatives], others)
                for invalid in ([], others + [others[0]], others + [country], [country], ["unsupported"]):
                    with self.assertRaises(ValueError):
                        ComparisonConfig.from_regions(invalid, home=country)

    def test_steam_amounts_use_hundredths_even_for_nonstandard_native_units(self):
        for country in ("jp", "kr", "kw", "vn", "cr"):
            currency = REGION_CURRENCIES[country]
            with self.subTest(currency=currency):
                raw = {"10": {"success": True, "data": {"price_overview": {
                    "currency": currency, "final": 12345, "initial": 24690, "discount_percent": 50}}}}
                price = SteamClient.parse_regional_price(raw, "10", country, currency, price_only=True)
                self.assertEqual(price.price.amount, 123.45)
                offer = parse_offer({"packageid": 100, "purchase_option_name": "Example",
                                     "final_price_in_cents": "12345", "original_price_in_cents": "24690"}, country, currency)
                self.assertEqual(offer["price"]["amount"], 123.45)
                with self.assertRaises(SteamRegionMismatchError):
                    SteamClient.parse_regional_price(raw, "10", country, "USD", price_only=True)

    def test_html_and_api_share_registry_and_full_selection_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = JobManager(directory, start_worker=False)
            app = WebApplication(manager)
            def request(path, body=None):
                raw = json.dumps(body).encode() if body is not None else b""
                env = {"HTTP_HOST": "127.0.0.1:8765", "HTTP_ORIGIN": "http://127.0.0.1:8765",
                       "REQUEST_METHOD": "POST" if body is not None else "GET", "PATH_INFO": path,
                       "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
                       "wsgi.input": io.BytesIO(raw), "REMOTE_ADDR": "test"}
                statuses = []
                content = b"".join(app(env, lambda status, headers: statuses.append(int(status[:3]))))
                return statuses[0], content
            status, content = request("/")
            self.assertEqual(status, 200)
            registry = json.loads(unescape(re.search(r'data-storefronts="([^"]+)"', content.decode()).group(1)))
            self.assertEqual(registry, dict(STOREFRONTS))
            selected = [country for country in STOREFRONTS if country != "jp"]
            status, _ = request("/api/jobs", {"identifier": "example", "home": "jp", "regions": selected})
            self.assertEqual(status, 202)
            for invalid in ([], selected + [selected[0]], ["jp"], ["zz"]):
                self.assertEqual(request("/api/jobs", {"identifier": "example", "home": "jp", "regions": invalid})[0], 400)
            with patch.object(manager.creator_search, "search", return_value={"exact_matches": []}) as search:
                self.assertEqual(request("/api/creators/search", {"query": "Studio", "home": "jp", "role": "developer"})[0], 200)
                self.assertEqual(search.call_args.args[2], "jp")

    def test_all_storefronts_reuse_observations_and_support_baseline_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = JobManager(Path(directory), start_worker=False)
            fixture = BatchHttpFixture(lambda app, country, code: RegionalPriceResult.available(
                StorePrice(country, code, 20, 40, 50), "Example"))
            with patch("steam_price_polisher.web_app.SteamClient") as steam, \
                 patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp, \
                 patch("steam_price_polisher.web_app.SteamBatchProvider", side_effect=lambda http, **kw: SteamBatchProvider(fixture, **kw)):
                steam.return_value.get_wishlist.return_value = WishlistResult((WishlistItem("10", "Example"),), "fixture")
                nbp.return_value.get_rate_details.side_effect = lambda codes: {
                    code: ExchangeRate(code, 1 + index, "2026-10-20") for index, code in enumerate(codes)}
                def execute(job):
                    self.assertIs(manager.queue.get_nowait(), job)
                    manager.execute(job); manager.queue.task_done()
                    self.assertEqual(job.data["state"], "complete", job.snapshot())
                    return job
                source = execute(manager.submit("76561198000000000", ComparisonConfig.from_regions(["us"]), "initial"))
                calls = len(fixture.calls)
                regions = [country for country in STOREFRONTS if country != "pl"]
                updated = execute(manager.change_currencies(source, ComparisonConfig.from_regions(regions), "all"))
                observed = set()
                for url in fixture.calls[calls:]:
                    query = parse_qs(urlsplit(url).query)
                    observed.add(json.loads(query["input_json"][0])["context"]["country_code"].lower()
                                 if "input_json" in query else query["cc"][0])
                self.assertEqual(observed, set(STOREFRONTS) - {"pl", "us"})
                row = updated.data["items"][0]
                self.assertEqual(len(row["comparison"]["alternatives"]), 36)
                self.assertEqual(len(row["best_offer_comparison"]["alternatives"]), 36)
                self.assertEqual(set(row["best_offers"]), set(STOREFRONTS))
                calls = len(fixture.calls)
                execute(manager.change_currencies(updated, ComparisonConfig.from_regions(
                    [country for country in STOREFRONTS if country != "jp"], home="jp"), "swap"))
                self.assertEqual(len(fixture.calls), calls)
                steam.return_value.get_wishlist.assert_called_once()
                self.assertEqual(len(source.data["items"][0]["comparison"]["alternatives"]), 1)
