import io
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from steam_price_polisher.creators import (
    CATALOG_CACHE_TTL, CATALOG_PAGE_SIZE, FEATURED_CREATORS, CreatorCatalogService, parse_catalog,
    CreatorSearchService, credit_creator, validate_selector, selector_id,
)
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.models import ExchangeRate, RegionalPriceResult, StorePrice
from steam_price_polisher.web_app import JobManager, WebApplication


def catalog_payload(start=0, total=3, products=None):
    products = products or [("1145360", "Hades"), ("2950840", "Hades II Original Soundtrack"), ("10", "A &amp; B")]
    # Steam includes app IDs on both the hover wrapper and the product link.
    html = "".join(f'<div><a data-ds-appid="{app_id}"></a><a class="store_capsule price_inline" '
                   f'data-ds-appid="{app_id}"><img alt="{name}"></a></div>' for app_id, name in products)
    return {"success": 1, "start": str(start), "pagesize": str(CATALOG_PAGE_SIZE),
            "total_count": total, "results_html": html}


class CatalogTests(unittest.TestCase):
    def test_credit_catalog_preserves_names_and_skips_bundles_without_stalling(self):
        payload = {"success": 1, "start": 12, "total_count": 40, "results_html":
                   '<a class="search_result_row" data-ds-appid="10"><span class="title">A &amp; B</span></a>'
                   '<a class="search_result_row" data-ds-appid="11" href="https://store.steampowered.com/bundle/123/Bundle/"></a>'}
        page = parse_catalog(payload, 12, search=True)
        self.assertEqual(page["products"], [{"app_id": "10", "name": "A & B", "date_added": None, "priority": None}])
        self.assertEqual(page["next_start"], 24)
        self.assertTrue(page["has_more"])
        empty = parse_catalog({"success": 1, "start": -1, "total_count": 0, "results_html": ""}, 0, search=True)
        self.assertFalse(empty["has_more"])
        for change in ({"start": 0}, {"results_html": "<html>Unexpected</html>"},
                       {"results_html": '<a class="search_result_row" data-ds-appid="../x"></a>'}):
            with self.subTest(change=change), self.assertRaises(HttpClientError):
                parse_catalog({**payload, **change}, 12, search=True)

    def test_credit_catalog_advances_through_steam_default_page_size(self):
        html = ''.join(f'<a class="search_result_row" data-ds-appid="{i}"><span class="title">Game</span></a>' for i in range(1, 25))
        html += '<a class="search_result_row" href="https://store.steampowered.com/bundle/123/Bundle/"></a>'
        page = parse_catalog({"success": 1, "start": 0, "total_count": 56, "results_html": html}, 0, search=True)
        self.assertEqual(len(page["products"]), 24)
        self.assertEqual(page["next_start"], 25)
        self.assertTrue(page["has_more"])

    def test_credit_catalog_encodes_name_and_separates_role_cache(self):
        from urllib.parse import parse_qs, urlsplit
        service, client = CreatorCatalogService(lambda: 0), Mock()
        client.get_json.return_value = {"success": 1, "start": -1, "total_count": 0, "results_html": ""}
        for kind in ("developer", "publisher"):
            creator = credit_creator({"kind": kind, "name": "A & B / Studio"})
            service.get_page(client, creator, "gb", 0)
            query = parse_qs(urlsplit(client.get_json.call_args.args[0]).query)
            self.assertEqual(query[kind], ["A & B / Studio"])
            self.assertEqual(query["cc"], ["GB"])
        self.assertEqual(client.get_json.call_count, 2)

    def test_parses_products_once_without_filtering_soundtracks_and_decodes_names(self):
        page = parse_catalog(catalog_payload(), 0)
        self.assertEqual([item["app_id"] for item in page["products"]], ["1145360", "2950840", "10"])
        self.assertEqual(page["products"][2]["name"], "A & B")
        self.assertFalse(page["has_more"])
        self.assertEqual(page["next_start"], CATALOG_PAGE_SIZE)

    def test_advances_steam_cursor_and_rejects_broken_or_wrong_pages(self):
        page = parse_catalog(catalog_payload(start=12, total=40), 12)
        self.assertEqual(page["next_start"], 24)
        self.assertTrue(page["has_more"])
        for changes in ({"start": 0}, {"pagesize": 0}, {"pagesize": True}, {"total_count": -1},
                        {"results_html": "<script>private()</script>"}, {"success": False},
                        {"results_html": '<a class="store_capsule" data-ds-appid="../secret"><img alt="Bad"></a>'}):
            with self.subTest(changes=changes), self.assertRaises(HttpClientError):
                parse_catalog({**catalog_payload(start=12, total=40), **changes}, 12)

    def test_page_cache_is_region_specific_and_denial_never_uses_stale_fallback(self):
        clock = Mock(return_value=0)
        service = CreatorCatalogService(clock)
        client = Mock()
        client.get_json.return_value = catalog_payload()
        self.assertEqual(service.get_page(client, "supergiant", "pl", 0)["source"], "live")
        self.assertEqual(service.get_page(client, "supergiant", "pl", 0)["source"], "cache")
        service.get_page(client, "supergiant", "gb", 0)
        self.assertEqual(client.get_json.call_count, 2)
        self.assertIn("cc=GB", client.get_json.call_args.args[0])
        clock.return_value = CATALOG_CACHE_TTL + 1
        client.get_json.side_effect = HttpClientError("outage", transient=True)
        self.assertEqual(service.get_page(client, "supergiant", "pl", 0)["source"], "stale cache")
        client.get_json.side_effect = HttpClientError("denied", network_access_denied=True)
        with self.assertRaises(HttpClientError):
            service.get_page(client, "supergiant", "pl", 0)


class CreatorSearchTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.client = Mock(return_value=0), Mock()
        self.service = CreatorSearchService(self.clock)
        self.service.role_catalogs = Mock()
        self.service.role_catalogs.get_page.return_value = {"total": 1, "source": "live"}
        self.item = {"item_type": 5, "id": 32938395, "success": 1, "name": "ConcernedApe",
                     "store_url_path": "developer/ConcernedApe"}
        self.client.get_json.return_value = {"response": {"metadata": {"count": 1}, "store_items": [self.item]}}

    def test_search_filters_noncreators_deduplicates_and_caches_by_region(self):
        self.client.get_json.return_value["response"]["store_items"] += [self.item, {"item_type": 0},
            {**self.item, "store_url_path": "franchise/Example"}, {**self.item, "store_url_path": "https://evil.test/"}]
        data = self.service.search(self.client, "ConcernedApe", "pl")
        self.assertEqual(len(data["creators"]), 1)
        self.assertEqual(data["creators"][0]["selector"], {"kind": "homepage", "clan_id": "32938395"})
        self.assertEqual([c["selector"]["kind"] for c in data["exact_matches"]], ["developer", "publisher"])
        self.service.search(self.client, "concernedape", "pl")
        self.assertEqual(self.client.get_json.call_count, 1)
        self.service.search(self.client, "ConcernedApe", "gb")
        self.clock.return_value = 601
        self.service.search(self.client, "ConcernedApe", "pl")
        self.assertEqual(self.client.get_json.call_count, 3)

    def test_empty_search_is_distinct_from_malformed_and_denied_responses(self):
        self.client.get_json.return_value = {"response": {"metadata": {"count": 0}}}
        self.service.role_catalogs.get_page.return_value = {"total": 0, "source": "live"}
        self.assertEqual(self.service.search(self.client, "no such studio", "pl"),
                         {"creators": [], "exact_matches": []})
        for payload in ({}, {"response": {}}, {"response": {"metadata": {}, "store_items": "bad"}}):
            self.client.get_json.return_value = payload
            with self.assertRaises(HttpClientError):
                self.service.search(self.client, "different", "pl")
        self.clock.return_value = 601
        self.client.get_json.side_effect = HttpClientError("denied", network_access_denied=True)
        with self.assertRaises(HttpClientError):
            self.service.search(self.client, "no such studio", "pl")

    def test_roles_are_verified_for_suggested_names_and_the_exact_query(self):
        self.service.role_catalogs = CreatorCatalogService(self.clock)
        self.client.get_json.side_effect = [
            {"response": {"metadata": {"count": 1}, "store_items": [self.item]}},
            {"success": 1, "start": 0, "total_count": 1, "results_html":
             '<a class="search_result_row" data-ds-appid="10"><span class="title">Game</span></a>'},
            {"success": 1, "start": -1, "total_count": 0, "results_html": ""},
            {"success": 1, "start": -1, "total_count": 0, "results_html": ""},
            {"success": 1, "start": -1, "total_count": 0, "results_html": ""},
        ]
        data = self.service.search(self.client, "Concerned", "pl")
        self.assertEqual([c["selector"] for c in data["exact_matches"]],
                         [{"kind": "developer", "name": "ConcernedApe"}])
        self.assertEqual(self.client.get_json.call_count, 5)
        self.service.search(self.client, "Concerned", "pl")
        self.assertEqual(self.client.get_json.call_count, 5)

    def test_role_search_only_checks_requested_role_and_separates_cache(self):
        developer = self.service.search(self.client, "ConcernedApe", "pl", "developer")
        self.assertEqual(developer["creators"], [])
        self.assertEqual([c["selector"]["kind"] for c in developer["exact_matches"]], ["developer"])
        self.assertEqual(self.service.role_catalogs.get_page.call_count, 1)
        publisher = self.service.search(self.client, "ConcernedApe", "pl", "publisher")
        self.assertEqual([c["selector"]["kind"] for c in publisher["exact_matches"]], ["publisher"])
        self.assertEqual(self.service.role_catalogs.get_page.call_count, 2)
        self.service.search(self.client, "ConcernedApe", "pl", "developer")
        self.assertEqual(self.client.get_json.call_count, 2)

    def test_role_verification_failure_does_not_cache_unverified_results(self):
        for failure in (HttpClientError("outage", transient=True),
                        HttpClientError("denied", network_access_denied=True)):
            with self.subTest(failure=failure):
                self.service.role_catalogs.get_page.side_effect = failure
                with self.assertRaises(HttpClientError):
                    self.service.search(self.client, "ConcernedApe", "pl")
                self.assertFalse(self.service.cache)
        self.service.role_catalogs.get_page.side_effect = None
        self.service.role_catalogs.get_page.return_value = {"total": 1, "source": "stale cache"}
        with self.assertRaises(HttpClientError):
            self.service.search(self.client, "ConcernedApe", "pl")
        self.assertFalse(self.service.cache)

    def test_resolve_checks_id_and_rejects_arbitrary_curators(self):
        selected = {"kind": "homepage", "clan_id": "32938395"}
        self.assertEqual(self.service.resolve(self.client, selected, "pl").name, "ConcernedApe")
        self.client.get_json.return_value["response"]["store_items"] = [{**self.item, "store_url_path": "curator/32938395"}]
        with self.assertRaises(HttpClientError):
            self.service.resolve(self.client, selected, "pl")
        self.client.get_json.return_value["response"]["store_items"] = [{**self.item, "id": 123}]
        with self.assertRaises(HttpClientError):
            self.service.resolve(self.client, selected, "pl")

    def test_selectors_reject_urls_unknown_fields_and_invalid_ids(self):
        for value in (None, {}, {"kind": []}, {"kind": "homepage", "clan_id": "1/../2"},
                      {"kind": "homepage", "clan_id": "4294967296"}, {"kind": "developer", "name": "a"},
                      {"kind": "developer", "name": "bad\ud800"},
                      {"kind": "publisher", "name": "Good", "url": "https://evil.test"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_selector(value)


class CreatorApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.manager = JobManager(self.directory.name, start_worker=False)
        self.manager.gate = Mock()
        self.app = WebApplication(self.manager)

    def request(self, path, method="GET", body=None, token="", **overrides):
        raw = json.dumps(body).encode() if body is not None else b""
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "HTTP_HOST": "127.0.0.1:8765",
                   "HTTP_ORIGIN": "http://127.0.0.1:8765", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
                   "HTTP_AUTHORIZATION": "Bearer " + token, "REMOTE_ADDR": "creator-test", **overrides}
        response = {}
        def start(status, headers):
            response.update(status=int(status.split()[0]), headers=dict(headers))
        data = b"".join(self.app(environ, start))
        response["data"] = json.loads(data) if response["headers"]["Content-Type"].startswith("application/json") else data
        return response

    def submit(self, **source):
        result = self.request("/api/creator-jobs", "POST", {"mode": "featured", "home": "pl", "regions": ["us", "de"], **source})
        self.assertEqual(result["status"], 202)
        return self.manager.jobs[result["data"]["id"]]

    def execute(self, job, free_ids=()):
        with patch("steam_price_polisher.web_app.SteamClient") as steam, patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp:
            nbp.return_value.get_rate_details.return_value = {
                "USD": ExchangeRate("USD", 4, "2026-10-02"), "EUR": ExchangeRate("EUR", 4.3, "2026-10-02")}
            steam.return_value.get_regional_price.side_effect = lambda app, region, currency: (
                RegionalPriceResult.no_regional_price("Demo", is_free=True) if app in free_ids else
                RegionalPriceResult.available(StorePrice(region, currency, 10, 20, 50), "Live product"))
            self.manager.execute(job)
            steam.return_value.get_wishlist.assert_not_called()
            return steam.return_value.get_regional_price.call_count

    def test_registry_and_assets_are_public_but_jobs_require_private_tokens(self):
        registry = self.request("/api/creators")["data"]["creators"]
        self.assertEqual(len(registry), 3)
        self.assertTrue(all(len(creator["examples"]) == 3 for creator in registry))
        for asset in ("/creators.js", "/steam-logo.svg"):
            self.assertEqual(self.request(asset)["status"], 200)
        job = self.submit()
        self.assertEqual(self.request("/api/jobs/" + job.id)["status"], 404)
        result = self.request("/api/jobs/" + job.id, token=job.token)["data"]
        self.assertEqual(result["profile"], "")
        self.assertEqual(result["source"], "creators")
        self.assertEqual(self.request("/api/jobs/" + job.id + "/cancel", "POST", {}, job.token)["data"]["state"], "cancelling")

    def test_featured_prices_reuse_normal_cache_and_have_creator_membership(self):
        job = self.submit()
        self.assertEqual(self.execute(job), 27)
        data = job.snapshot()
        self.assertEqual(data["state"], "complete")
        self.assertEqual(len(data["items"]), 9)
        self.assertEqual(data["items"][0]["creator_ids"], ["supergiant"])
        expected = [item.app_id for creator in FEATURED_CREATORS for item in creator.examples]
        self.assertEqual([item["app_id"] for item in data["items"]], expected)
        second = self.submit(mode="products", app_ids=expected)
        self.assertEqual(self.execute(second), 0)
        self.assertEqual(len(second.snapshot()["items"]), 9)
        self.assertTrue(all(item["source_summary"] == "cache 3" for item in second.snapshot()["items"]))

    def test_free_products_are_identified_and_cached_without_alternative_requests(self):
        job = self.submit(mode="products", app_ids=["10", "11"])
        self.assertEqual(self.execute(job, free_ids={"10"}), 4)
        items = job.snapshot()["items"]
        self.assertTrue(items[0]["is_free"])
        self.assertFalse(items[1]["is_free"])
        self.assertEqual(job.snapshot()["state"], "complete")
        second = self.submit(mode="products", app_ids=["10", "11"])
        self.assertEqual(self.execute(second, free_ids={"10"}), 0)
        self.assertTrue(second.snapshot()["items"][0]["is_free"])

    def test_catalog_products_use_existing_comparison_pipeline_and_keep_cursor(self):
        job = self.submit(mode="catalog", creator_id="supergiant", start=12)
        with patch.object(self.manager.catalogs, "get_page", return_value={**parse_catalog(catalog_payload(start=12, total=40), 12), "source": "live"}) as get_page:
            self.execute(job)
        self.assertEqual(job.snapshot()["state"], "complete")
        self.assertEqual(job.snapshot()["catalogs"]["supergiant"]["next_start"], 24)
        self.assertIn("2950840", [item["app_id"] for item in job.snapshot()["items"]])
        self.assertEqual(get_page.call_args.args[1:], ("supergiant", "pl", 12))

    def test_catalog_permission_denial_stops_without_price_requests(self):
        job = self.submit(mode="catalog", creator_id="supergiant")
        with patch.object(self.manager.catalogs, "get_page", side_effect=HttpClientError("private detail", network_access_denied=True)):
            self.manager.execute(job)
        self.assertEqual(job.snapshot()["error_code"], "network_access_denied")
        self.assertEqual(job.snapshot()["items"], [])
        self.assertNotIn("private detail", json.dumps(job.snapshot()))

    def test_request_validation_and_origin_checks_prevent_arbitrary_catalog_urls(self):
        invalid = ({"creator_id": "https://localhost/secret", "mode": "catalog"}, {"mode": []},
                   {"mode": "catalog", "creator_id": "supergiant", "start": True},
                   {"mode": "catalog", "creator_id": "supergiant", "start": -1},
                   {"mode": "featured", "start": 0}, {"mode": "search"}, {"regions": []},
                   {"mode": "products", "app_ids": ["../private"]},
                   {"mode": "products", "app_ids": ["10", "10"]}, {"mode": "products", "app_ids": [10]},
                   {"mode": "products", "app_ids": []}, {"mode": "products", "app_ids": [str(i) for i in range(1001)]})
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(self.request("/api/creator-jobs", "POST", {"mode": "featured", "regions": ["us"], **changes})["status"], 400)
        self.assertEqual(self.request("/api/creator-jobs", "POST", {"mode": "featured", "regions": ["us"]}, HTTP_ORIGIN="https://evil.test")["status"], 403)
        self.assertFalse(self.manager.jobs)

    def test_wishlist_and_creators_share_the_worker_busy_limit(self):
        self.submit()
        response = self.request("/api/jobs", "POST", {"identifier": "example", "regions": ["us"]})
        self.assertEqual(response["status"], 429)

    def test_creator_search_validates_origin_inputs_busy_state_and_sanitizes_failure(self):
        path, body = "/api/creators/search", {"query": "Valve", "home": "pl"}
        with patch.object(self.manager.creator_search, "search", return_value={"creators": [], "exact_matches": []}) as search:
            self.assertEqual(self.request(path, "POST", body)["status"], 200)
            search.assert_called_once()
            self.assertEqual(self.request(path, "POST", body, HTTP_ORIGIN="https://evil.test")["status"], 403)
            for changes in ({"query": "x"}, {"home": "xx"}, {"home": []}, {"query": []}, {"url": "https://evil.test"}):
                self.assertEqual(self.request(path, "POST", {**body, **changes})["status"], 400)
            with self.manager.creator_search.lock:
                self.assertEqual(self.request(path, "POST", body)["status"], 429)
        with patch.object(self.manager.creator_search, "search", side_effect=HttpClientError("secret URL")):
            response = self.request(path, "POST", body)
        self.assertEqual(response["status"], 503)
        self.assertNotIn("secret", json.dumps(response))
        self.assertFalse(self.manager.creator_search.lock.locked())

    def test_featured_registry_separates_roles_and_uses_credit_selectors(self):
        data = self.request("/api/creators")["data"]
        self.assertEqual([c["name"] for c in data["developers"]], ["Supergiant Games", "CD PROJEKT RED", "Techland"])
        self.assertEqual([c["name"] for c in data["publishers"]],
                         ["Devolver Digital", "THQ Nordic", "11 bit studios"])
        self.assertTrue(set(c["name"] for c in data["developers"]).isdisjoint(
            c["name"] for c in data["publishers"]))
        for key, kind in (("developers", "developer"), ("publishers", "publisher")):
            for catalog in data[key]:
                self.assertEqual(catalog["selector"], {"kind": kind, "name": catalog["name"]})
                self.assertEqual(catalog["id"], selector_id(catalog["selector"]))
                self.assertEqual(len(catalog["examples"]), 3)
                from steam_price_polisher.web_app import validate_creator_request
                _, source = validate_creator_request({"mode": "catalog", "regions": ["us"],
                                                      "creator_id": catalog["id"], "selector": catalog["selector"]})
                self.assertEqual(source["selector"], catalog["selector"])

    def test_search_role_validation_and_dispatch(self):
        body = {"query": "Valve", "home": "pl", "role": "publisher"}
        with patch.object(self.manager.creator_search, "search", return_value={"creators": [], "exact_matches": []}) as search:
            self.assertEqual(self.request("/api/creators/search", "POST", body)["status"], 200)
            self.assertEqual(search.call_args.args[1:], ("Valve", "pl", "publisher"))
            for role in (None, "homepage", [], "unknown"):
                self.assertEqual(self.request("/api/creators/search", "POST", {**body, "role": role})["status"], 400)

    def test_dynamic_homepage_uses_existing_pipeline_and_revalidates_identity(self):
        selector = {"kind": "homepage", "clan_id": "32938395"}
        job = self.submit(mode="catalog", creator_id=selector_id(selector), selector=selector)
        creator = credit_creator({"kind": "developer", "name": "Example"})
        with patch.object(self.manager.creator_search, "resolve", return_value=creator) as resolve, patch.object(
                self.manager.catalogs, "get_page", return_value={**parse_catalog(catalog_payload(), 0), "source": "live"}):
            self.execute(job)
        resolve.assert_called_once()
        self.assertEqual(job.snapshot()["state"], "complete")
        self.assertEqual(job.snapshot()["items"][0]["creator_ids"], [selector_id(selector)])
        response = self.request("/api/creator-jobs", "POST", {"mode": "catalog", "regions": ["us"], "creator_id": "wrong", "selector": selector})
        self.assertEqual(response["status"], 400)

    def test_empty_dynamic_catalog_finishes_without_rate_or_price_requests(self):
        selector = {"kind": "developer", "name": "Unknown studio"}
        job = self.submit(mode="catalog", creator_id=selector_id(selector), selector=selector)
        with patch.object(self.manager.catalogs, "get_page", return_value={"products": [], "total": 0,
                "has_more": False, "next_start": 12, "source": "live"}), patch("steam_price_polisher.web_app.NbpExchangeRateProvider") as nbp:
            self.manager.execute(job)
        nbp.assert_not_called()
        self.assertEqual(job.snapshot()["state"], "complete")
        self.assertEqual(job.snapshot()["items"], [])
