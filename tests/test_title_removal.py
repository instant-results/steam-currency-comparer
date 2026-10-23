"""Permanent comparison cleanup after the browser's bounded Undo window."""
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.models import WishlistItem
from steam_price_polisher.web_app import BusyError, JobManager, WebApplication


class TitleRemovalTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.manager = JobManager(directory.name, start_worker=False)
        self.app = WebApplication(self.manager)
        self.job = self.manager.submit("example", ComparisonConfig(), "first",
            creator_request={"mode": "products", "app_ids": ["1", "2"]})
        self.job.loaded_items = (WishlistItem("1", "First"), WishlistItem("2", "Second"))
        self.job.creator_membership = {"1": ["studio", "other"], "2": ["studio"]}
        self.job.update(state="complete", total=2,
            items=[{"app_id": "1", "name": "First"}, {"app_id": "2", "name": "Second"}],
            catalogs={name: {"products": [{"app_id": "1", "name": "First"}], "next_start": 25}
                      for name in ("studio", "other")})

    def request(self, body, token=None, **headers):
        raw = json.dumps(body).encode()
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": f"/api/jobs/{self.job.id}/remove",
            "HTTP_HOST": "127.0.0.1:8765", "HTTP_ORIGIN": "http://127.0.0.1:8765",
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw), "HTTP_AUTHORIZATION": "Bearer " + (self.job.token if token is None else token),
            **headers}
        response = {}
        def start(status, headers):
            response["status"] = int(status.split()[0])
        response["body"] = json.loads(b"".join(self.app(env, start)))
        return response

    def test_cleanup_removes_all_memberships_and_source_selection_and_is_idempotent(self):
        previous = self.job.snapshot()
        self.assertEqual(self.request({"app_ids": ["1"]})["status"], 200)
        self.assertEqual(self.request({"app_ids": ["1"]})["status"], 200)
        self.assertEqual(self.job.data["items"], [{"app_id": "2", "name": "Second"}])
        self.assertEqual([item.app_id for item in self.job.loaded_items], ["2"])
        self.assertEqual(self.job.creator_request["app_ids"], ["2"])
        self.assertNotIn("1", self.job.creator_membership)
        self.assertEqual(self.job.data["total"], 1)
        for page in self.job.data["catalogs"].values():
            self.assertEqual(page["products"], [])
            self.assertEqual(page["next_start"], 25)
        self.assertEqual(len(previous["catalogs"]["studio"]["products"]), 1)

    def test_late_results_are_rejected_and_other_jobs_are_independent(self):
        other = self.manager.submit("example", ComparisonConfig(), "other")
        other.append({"app_id": "1", "name": "First"})
        self.job.remove_titles(["1", "99"])
        self.job.append({"app_id": "1", "name": "First"})
        self.job.append({"app_id": "99", "name": "Late result"})
        self.assertEqual([row["app_id"] for row in self.job.snapshot()["items"]], ["2"])
        self.assertEqual(len(other.snapshot()["items"]), 1)

    def test_currency_child_retains_exclusions_and_does_not_alias_source_requests(self):
        self.job.remove_titles(["1"])
        child = self.manager.change_currencies(self.job, ComparisonConfig.from_regions(["gb"]), "child")
        self.assertEqual(child.excluded_app_ids, {"1"})
        self.assertEqual([item.app_id for item in child.loaded_items], ["2"])
        child.remove_titles(["2"])
        self.assertEqual(self.job.creator_request["app_ids"], ["2"])
        self.assertEqual(child.creator_request["app_ids"], [])

    def test_endpoint_requires_own_token_origin_and_valid_bounded_ids(self):
        self.assertEqual(self.request({"app_ids": ["1"]}, token="invalid")["status"], 404)
        self.assertEqual(self.request({"app_ids": ["1"]}, HTTP_ORIGIN="https://evil.test")["status"], 403)
        for body in (None, [], {}, {"app_ids": []}, {"app_ids": [1]}, {"app_ids": ["1", "1"]},
                     {"app_ids": ["../bad"]}, {"app_ids": ["1"], "price": 0},
                     {"app_ids": [str(i) for i in range(10001)]}):
            with self.subTest(body_type=type(body).__name__):
                self.assertEqual(self.request(body)["status"], 400)
        self.assertEqual(len(self.job.data["items"]), 2)

    def test_exclusions_are_validated_on_recreated_wishlist_and_catalog_jobs(self):
        from steam_price_polisher.web_app import validate_request, validate_creator_request, InputError
        for exclusions in ("1", [True], ["1", "1"], ["x"], [str(i) for i in range(10001)]):
            with self.assertRaises(InputError):
                validate_request({"identifier": "example", "regions": ["us"], "excluded_app_ids": exclusions})
            with self.assertRaises(InputError):
                validate_creator_request({"mode": "products", "app_ids": ["1"], "regions": ["us"], "excluded_app_ids": exclusions})
        validate_request({"identifier": "example", "regions": ["us"], "excluded_app_ids": ["1"]})

    def test_library_cleanup_respects_disabled_feature_flag(self):
        self.job.library = True
        self.assertEqual(self.request({"app_ids": ["1"]})["status"], 404)
        self.assertEqual(len(self.job.data["items"]), 2)

    def test_sequential_jobs_have_no_per_minute_limit_after_cleanup(self):
        owner = "rate-limit-browser"
        with patch("steam_price_polisher.web_app.time.monotonic", return_value=1000):
            sources = []
            for _ in range(3):
                source = self.manager.submit("example", ComparisonConfig(), owner)
                source.loaded_items = (WishlistItem("1", "First"), WishlistItem("2", "Second"))
                source.update(state="complete", total=2,
                              items=[{"app_id": "1"}, {"app_id": "2"}])
                sources.append(source)
        with patch("steam_price_polisher.web_app.time.monotonic", return_value=1001):
            for source in sources:
                source.remove_titles(["1"])
            updated = self.manager.change_currencies(sources[-1], ComparisonConfig(), owner)
            self.assertEqual([item.app_id for item in updated.loaded_items], ["2"])
            updated.update(state="complete")
            for _ in range(2):
                fresh = self.manager.submit("example", ComparisonConfig(), owner)
                fresh.update(state="complete")
            fresh = self.manager.submit("example", ComparisonConfig(), owner)
            with self.assertRaisesRegex(BusyError, "already running"):
                self.manager.submit("example", ComparisonConfig(), owner)
            fresh.update(state="complete")
            self.manager.max_jobs = 1
            self.manager.submit("example", ComparisonConfig(), owner)
            with self.assertRaisesRegex(BusyError, "service is busy"):
                self.manager.submit("example", ComparisonConfig(), "another-browser")

    def test_cleanup_accepts_ten_thousand_ids_in_a_request(self):
        ids = [str(100000000000 + i) for i in range(10000)]
        self.assertEqual(self.request({"app_ids": ids})["status"], 200)
        self.assertEqual(len(self.job.excluded_app_ids), 10000)
        self.assertEqual(self.request({"app_ids": ["999"]})["status"], 400)
