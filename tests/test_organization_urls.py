import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from steam_price_polisher.creators import CreatorSearchService, credit_creator, validate_search_query
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.organization_urls import (
    HomepageRedirect, HomepageRedirectHandler, OrganizationHttpClient,
    parse_homepage, parse_organization_url,
)


def homepage(clan=123, creator=True):
    return ('<script>var g_pagingData = ' + json.dumps({"clanid": clan})
            + '; var g_bIsCreatorHome = ' + str(creator).lower() + ';</script>'
            + '<a href="https://store.steampowered.com/app/10/Example/">Example</a>')


class OrganizationAddressTests(unittest.TestCase):
    def test_four_homepage_aliases_hosts_and_subpages_are_canonicalized(self):
        for prefix in ("developer", "publisher", "dev", "pub"):
            for host in ("store.steampowered.com", "www.steampowered.com", "steampowered.com"):
                with self.subTest(prefix=prefix, host=host):
                    address = parse_organization_url(f"http://{host}/{prefix}/Studio%20Name/about/?l=polish&snr=tracking#top")
                    self.assertEqual(address, {"kind": "homepage", "url": f"https://store.steampowered.com/{prefix}/Studio%20Name/"})
        self.assertEqual(parse_organization_url("store.steampowered.com/dev/Example")["kind"], "homepage")

    def test_numeric_curator_urls_keep_the_id_and_discard_display_slug(self):
        self.assertEqual(parse_organization_url("https://store.steampowered.com/curator/123-Studio-Name/games/?x=y"),
                         {"kind": "homepage", "url": "https://store.steampowered.com/curator/123/", "clan_id": "123"})

    def test_search_links_preserve_the_exact_credit_name(self):
        for role in ("developer", "publisher"):
            self.assertEqual(parse_organization_url(f"https://store.steampowered.com/search/?{role}=A+%26+B&snr=x"),
                             {"kind": "credit", "role": role, "name": "A & B"})

    def test_unsupported_ambiguous_and_host_confusion_urls_are_rejected(self):
        invalid = ["https://evil.test/developer/Studio", "https://store.steampowered.com.evil.test/dev/X",
                   "https://user@store.steampowered.com/dev/X", "https://store.steampowered.com:443/dev/X",
                   "file://store.steampowered.com/dev/X", "https://store.steampowered.com/dev/../",
                   "https://store.steampowered.com/dev/%2e%2e/", "https://store.steampowered.com/dev/%2fsecret/",
                   "https://store.steampowered.com/franchise/Studio", "https://store.steampowered.com/app/10/",
                   "https://store.steampowered.com/curator/4294967296/", "https://store.steampowered.com/dev/X/admin",
                   "https://store.steampowered.com/search/?developer=First&developer=Second",
                   "https://store.steampowered.com/search/?developer=First&publisher=Second",
                   "https://store.steampowered.com/search/?developer=", "https://store.steampowered.com/search/?term=X",
                   "https://store.steampowered.com/dev/Bad\nName", "https://store.steampowered.com/dev/Bad\\Name",
                   "https://store.steampowered.com/dev/%ZZ", "https://store.steampowered.com/dev/" + "a" * 1024]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_organization_url(value)

    def test_query_length_limits_distinguish_names_and_urls(self):
        self.assertEqual(validate_search_query("Studio: Name"), "Studio: Name")
        with self.assertRaises(ValueError):
            validate_search_query("a" * 101)
        url = "https://store.steampowered.com/dev/Studio/?snr=" + "a" * 200
        self.assertEqual(validate_search_query(url), url)

    def test_homepage_parser_requires_creator_marker_and_valid_identity(self):
        self.assertEqual(parse_homepage(homepage()), {"clan_id": "123", "app_ids": ["10"]})
        for value in (homepage(creator=False), homepage(clan=True), homepage(clan=4294967296), "<html>Error</html>"):
            with self.subTest(value=value), self.assertRaises(HttpClientError):
                parse_homepage(value)

    def test_homepage_sample_is_deduplicated_and_bounded(self):
        data = homepage() + ''.join(f'<a href="https://store.steampowered.com/app/{i}/">Game</a>' for i in range(1, 100))
        self.assertEqual(len(parse_homepage(data)["app_ids"]), 12)
        self.assertEqual(len(set(parse_homepage(data)["app_ids"])), 12)

    def test_redirects_are_validated_before_another_request(self):
        handler = HomepageRedirectHandler()
        with self.assertRaises(HomepageRedirect) as raised:
            handler.redirect_request(None, None, 302, "", {}, "https://store.steampowered.com/pub/Studio/?snr=x")
        self.assertEqual(raised.exception.url, "https://store.steampowered.com/pub/Studio/")
        for url in ("https://127.0.0.1/dev/Studio", "https://store.steampowered.com/login", "https://evil.test/dev/Studio"):
            with self.subTest(url=url), self.assertRaises(HttpClientError):
                handler.redirect_request(None, None, 302, "", {}, url)

    def test_modern_homepage_identity_does_not_require_legacy_paging_data(self):
        data = '<script>var g_bIsCreatorHome = true;</script><button onclick="FollowCurator(123, true);">Follow</button>'
        self.assertEqual(parse_homepage(data), {"clan_id": "123", "app_ids": []})
        with self.assertRaises(HttpClientError):
            parse_homepage(data + '<button onclick="FollowCurator(456, false);">Other</button>')

    def test_transport_reads_bounded_html_and_preserves_json_requests(self):
        client = OrganizationHttpClient()
        with patch.object(client._opener, "open", return_value=io.BytesIO(homepage().encode())):
            self.assertEqual(client.get_json("https://store.steampowered.com/dev/Studio/")["clan_id"], "123")
        with patch.object(client._opener, "open", return_value=io.BytesIO(b'{"response":{}}')):
            self.assertEqual(client.get_json("https://api.steampowered.com/example"), {"response": {}})
        with patch.object(client._opener, "open", return_value=io.BytesIO(b'{"success":1}')):
            self.assertEqual(client.get_json("https://store.steampowered.com/curator/123/ajaxgetfilteredrecommendations/"), {"success": 1})
        for raw in (b'x' * 2_000_001, b'\xff'):
            with patch.object(client._opener, "open", return_value=io.BytesIO(raw)), self.assertRaises(HttpClientError) as raised:
                client.get_json("https://store.steampowered.com/dev/Studio/")
            self.assertTrue(raised.exception.invalid_response)


class OrganizationResolutionTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.clock = Mock(return_value=0)
        self.service = CreatorSearchService(self.clock)
        self.service.role_catalogs = Mock()
        self.service.role_catalogs.get_page.return_value = {"total": 1, "source": "live"}
        self.credit = {"name": "Exact Studio", "creator_clan_account_id": 123}
        self.basic = {"developers": [self.credit], "publishers": []}
        def response(url):
            if url.startswith("https://store.steampowered.com/"):
                return {"clan_id": "123", "app_ids": ["10"]}
            request = json.loads(parse_qs(urlsplit(url).query)["input_json"][0])
            if "creatorid" in request["ids"][0]:
                return {"response": {"store_items": [{"id": 123, "item_type": 5, "success": 1,
                    "name": "Different Homepage Label", "store_url_path": "publisher/Studio"}]}}
            self.assertNotIn("include_best_purchase_option", request["data_request"])
            return {"response": {"store_items": [{"id": 10, "item_type": 0, "success": 1, "basic_info": self.basic}]}}
        self.client.get_json.side_effect = response

    def test_homepage_uses_linked_credit_name_and_existing_catalog_identity(self):
        data = self.service.search(self.client, "https://store.steampowered.com/publisher/Studio/", "pl", "developer")
        expected = credit_creator({"kind": "developer", "name": "Exact Studio"}).public()
        self.assertEqual(data, {"creators": [], "exact_matches": [expected]})
        self.assertEqual(self.client.get_json.call_count, 3)
        self.assertNotIn("price_overview", self.client.get_json.call_args.args[0])
        self.service.search(self.client, "https://store.steampowered.com/publisher/Studio/", "pl", "developer")
        self.assertEqual(self.client.get_json.call_count, 3)

    def test_same_homepage_can_supply_multiple_credit_names_and_both_roles(self):
        self.basic["developers"] += [{**self.credit, "name": "Another Studio"}, self.credit]
        self.basic["publishers"] = [self.credit]
        data = self.service.search(self.client, "https://store.steampowered.com/dev/Studio/", "pl", "developer")
        self.assertEqual([c["name"] for c in data["exact_matches"]], ["Exact Studio", "Another Studio"])
        self.assertNotIn("role_warning", data)

    def test_wrong_role_warning_requires_verified_opposite_credits(self):
        self.basic = {"publishers": [self.credit], "developers": []}
        data = self.service.search(self.client, "https://store.steampowered.com/developer/Studio/", "pl", "developer")
        self.assertEqual(data["exact_matches"], [])
        self.assertEqual(data["role_warning"]["role"], "publisher")
        self.assertIn("Publishers tab", data["role_warning"]["message"])

    def test_modern_homepage_uses_catalog_sample_before_credit_verification(self):
        original = self.client.get_json.side_effect
        self.client.get_json.side_effect = lambda url: {"clan_id": "123", "app_ids": []} if \
            url.startswith("https://store.steampowered.com/") else original(url)
        self.service.role_catalogs.get_page.return_value = {
            "total": 100, "source": "live", "products": [{"app_id": "10"}]}
        data = self.service.search(self.client, "https://store.steampowered.com/dev/Studio/", "pl", "developer")
        self.assertEqual(data["exact_matches"][0]["name"], "Exact Studio")
        self.assertEqual(self.service.role_catalogs.get_page.call_count, 2)
        self.assertEqual(self.service.role_catalogs.get_page.call_args_list[0].args[1].selector["kind"], "homepage")

    def test_unlinked_copublisher_and_same_named_unrelated_credits_are_excluded(self):
        self.basic = {"publishers": [{"name": "Unrelated", "creator_clan_account_id": 999}],
                      "developers": [{"name": "Different Homepage Label"}]}
        data = self.service.search(self.client, "https://store.steampowered.com/dev/Studio/", "pl", "developer")
        self.assertEqual(data["exact_matches"], [])
        self.assertNotIn("role_warning", data)
        self.assertIn("exact credit name", data["notice"])
        self.service.role_catalogs.get_page.assert_not_called()

    def test_search_url_needs_no_homepage_requests_and_keeps_current_tab_role(self):
        data = self.service.search(self.client, "https://store.steampowered.com/search/?publisher=Exact+Studio", "pl", "developer")
        self.assertEqual(data["exact_matches"][0]["selector"], {"kind": "developer", "name": "Exact Studio"})
        self.client.get_json.assert_not_called()

    def test_wrong_role_search_url_and_stale_verification(self):
        self.service.role_catalogs.get_page.side_effect = lambda client, creator, region, start: {
            "total": int(creator.selector["kind"] == "publisher"), "source": "live"}
        data = self.service.search(self.client, "https://store.steampowered.com/search/?publisher=Exact+Studio", "pl", "developer")
        self.assertEqual(data["role_warning"]["role"], "publisher")
        self.service.cache.clear()
        self.service.role_catalogs.get_page.side_effect = None
        self.service.role_catalogs.get_page.return_value = {"total": 1, "source": "stale cache"}
        with self.assertRaises(HttpClientError):
            self.service.search(self.client, "https://store.steampowered.com/search/?developer=Exact+Studio", "pl", "developer")
        self.assertFalse(self.service.cache)

    def test_denial_and_malformed_credits_fail_without_cached_success(self):
        self.basic["developers"] = [{**self.credit, "name": None}]
        with self.assertRaises(HttpClientError):
            self.service.search(self.client, "https://store.steampowered.com/dev/Studio/", "pl", "developer")
        self.client.get_json.side_effect = HttpClientError("denied", network_access_denied=True)
        with self.assertRaises(HttpClientError) as raised:
            self.service.search(self.client, "https://store.steampowered.com/dev/Studio/", "pl", "developer")
        self.assertTrue(raised.exception.network_access_denied)
        self.assertFalse(self.service.cache)

    def test_redirect_loops_and_numeric_identity_mismatch_fail(self):
        with self.assertRaises(HttpClientError):
            self.service.search(self.client, "https://store.steampowered.com/curator/456/", "pl", "developer")
        self.client.get_json.side_effect = HomepageRedirect("https://store.steampowered.com/dev/Loop/")
        with self.assertRaises(HttpClientError):
            self.service.search(self.client, "https://store.steampowered.com/dev/Loop/", "pl", "developer")
