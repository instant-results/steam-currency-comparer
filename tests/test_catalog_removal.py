"""Catalog ownership cleanup, including late discovery and currency children."""
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.models import WishlistItem
from steam_price_polisher.web_app import JobManager, WebApplication, InputError, validate_creator_request


class CatalogRemovalTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.manager = JobManager(directory.name, start_worker=False)
        self.app = WebApplication(self.manager)
        self.job = self.manager.submit("", ComparisonConfig(), "first", creator_request={
            "mode": "products", "app_ids": ["1", "2", "3"],
            "catalog_memberships": {"studio": ["1", "2"], "other": ["1", "3"]}})
        self.job.loaded_items = tuple(WishlistItem(str(i), f"Title {i}") for i in range(1, 4))
        self.job.creator_membership = {"1": ["studio", "other"], "2": ["studio"], "3": ["other"]}
        self.job.update(state="complete", total=3, items=[
            {"app_id": str(i), "name": f"Title {i}", "creator_ids": list(self.job.creator_membership[str(i)])}
            for i in range(1, 4)], catalogs={key: {"products": [{"app_id": app_id, "name": app_id} for app_id in ids]}
            for key, ids in self.job.creator_request["catalog_memberships"].items()})

    def request(self, payload, **overrides):
        raw = json.dumps(payload).encode()
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": f"/api/jobs/{self.job.id}/remove-catalogs",
               "HTTP_HOST": "127.0.0.1:8765", "HTTP_ORIGIN": "http://127.0.0.1:8765",
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw), "HTTP_AUTHORIZATION": "Bearer " + self.job.token, **overrides}
        response = {}
        def start(status, headers):
            response["status"] = int(status.split()[0])
        response["body"] = json.loads(b"".join(self.app(env, start)))
        return response

    def test_removal_preserves_shared_products_and_purges_private_group_records(self):
        before = self.job.snapshot()
        for _ in range(2):
            self.assertEqual(self.request({"catalog_ids": ["studio"], "app_ids": ["1", "2"]})["status"], 200)
        self.assertEqual([row["app_id"] for row in self.job.data["items"]], ["1", "3"])
        self.assertEqual(self.job.data["items"][0]["creator_ids"], ["other"])
        self.assertEqual(self.job.creator_membership, {"1": ["other"], "3": ["other"]})
        self.assertEqual(self.job.creator_request["app_ids"], ["1", "3"])
        self.assertEqual(list(self.job.creator_request["catalog_memberships"]), ["other"])
        self.assertEqual(list(self.job.data["catalogs"]), ["other"])
        self.assertEqual([item.app_id for item in self.job.loaded_items], ["1", "3"])
        self.assertEqual(self.job.data["total"], 2)
        self.assertIn("studio", before["catalogs"])
        self.assertEqual(before["items"][0]["creator_ids"], ["studio", "other"])

    def test_old_products_job_can_cleanup_explicit_orphans_without_memberships(self):
        self.job.creator_membership.clear()
        self.job.data["catalogs"].clear()
        self.job.creator_request.pop("catalog_memberships")
        self.assertEqual(self.request({"catalog_ids": ["studio"], "app_ids": ["2"]})["status"], 200)
        self.assertEqual(self.job.creator_request["app_ids"], ["1", "3"])
        self.job.append({"app_id": "2", "name": "Late"})
        self.assertNotIn("2", [row["app_id"] for row in self.job.data["items"]])

    def test_cleanup_during_discovery_blocks_late_catalog_and_product_publication(self):
        job = self.manager.submit("", ComparisonConfig(), "discovery", creator_request={
            "mode": "catalog", "creator_id": "supergiant", "start": 0})
        def page(*args):
            job.remove_catalogs(["supergiant"])
            return {"products": [{"app_id": "99", "name": "Late title"}], "next_start": 25, "has_more": False, "total": 1, "source": "live"}
        with patch.object(self.manager.catalogs, "get_page", side_effect=page):
            self.manager.execute(job)
        self.assertEqual(job.data["state"], "complete")
        self.assertEqual(job.data["catalogs"], {})
        self.assertEqual(job.loaded_items, ())
        self.assertEqual(job.data["items"], [])
        self.assertIn("99", job.excluded_app_ids)
        self.assertNotIn("creator_id", job.creator_request)

    def test_currency_child_retains_clean_memberships_and_exclusions(self):
        self.job.remove_catalogs(["studio"])
        child = self.manager.change_currencies(self.job, ComparisonConfig.from_regions(["gb"]), "child")
        self.assertEqual(child.excluded_catalog_ids, {"studio"})
        self.assertEqual([item.app_id for item in child.loaded_items], ["1", "3"])
        child.remove_catalogs(["other"])
        self.assertEqual(child.loaded_items, ())
        self.assertEqual([item.app_id for item in self.job.loaded_items], ["1", "3"])

    def test_endpoint_requires_private_token_origin_and_bounded_valid_ids(self):
        self.assertEqual(self.request({"catalog_ids": ["studio"]}, HTTP_AUTHORIZATION="Bearer wrong")["status"], 404)
        self.assertEqual(self.request({"catalog_ids": ["studio"]}, HTTP_ORIGIN="https://evil.test")["status"], 403)
        invalid = [None, {}, {"catalog_ids": []}, {"catalog_ids": ["studio", "studio"]},
                   {"catalog_ids": ["../bad"]}, {"catalog_ids": [1]}, {"catalog_ids": [str(i) for i in range(21)]},
                   {"catalog_ids": ["studio"], "app_ids": ["x"]},
                   {"catalog_ids": ["studio"], "app_ids": [str(i) for i in range(1001)]},
                   {"catalog_ids": ["studio"], "unknown": True}]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.request(body)["status"], 400)
        self.assertEqual(len(self.job.data["items"]), 3)
        self.job.creator_request = None
        self.assertEqual(self.request({"catalog_ids": ["studio"]})["status"], 400)

    def test_removal_limits_reject_atomically(self):
        self.job.excluded_catalog_ids = {f"old-{i}" for i in range(1000)}
        self.assertEqual(self.request({"catalog_ids": ["studio"]})["status"], 400)
        self.assertEqual(len(self.job.data["items"]), 3)
        self.assertIn("studio", self.job.data["catalogs"])

    def test_explicit_product_memberships_are_bounded_and_must_match_selection(self):
        base = {"mode": "products", "app_ids": ["1", "2"], "regions": ["us"]}
        payload = {**base, "catalog_memberships": {"studio": ["1"], "other": ["1", "2"]}}
        _, result = validate_creator_request(payload)
        payload["catalog_memberships"]["studio"].clear()
        self.assertEqual(result["catalog_memberships"]["studio"], ["1"])
        for memberships in ([], {"../bad": ["1"]}, {"studio": ["3"]}, {"studio": ["1", "1"]},
                            {"studio": [True]}, {"studio": [["1"]]}, {str(i): [] for i in range(21)}):
            with self.subTest(memberships=memberships), self.assertRaises(InputError):
                validate_creator_request({**base, "catalog_memberships": memberships})
        with self.assertRaises(InputError):
            validate_creator_request({"mode": "featured", "regions": ["us"], "catalog_memberships": {}})
