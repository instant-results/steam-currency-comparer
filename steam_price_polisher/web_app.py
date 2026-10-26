"""Same-origin WSGI web app with bounded, private, cancellable analysis jobs.

One analysis worker shares the Steam pacing gate. Deploy with one WSGI process;
job state is in memory and expires after one hour. Regional price cache persists.
"""
from __future__ import annotations

import hmac
from html import escape
import json
import os
import queue
import re
import secrets
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .analysis import AnalysisRunner, WISHLIST_ORDERS, STEAM_WISHLIST_ORDERS, deduplicate_wishlist
from .cache import SQLiteCache
from .configuration import ComparisonConfig, MAX_COMPARISONS, STOREFRONTS
from .exchange_rates import CachedExchangeRateProvider, NbpExchangeRateProvider
from .games import GameSearch
from .http_client import HttpClientError, UrllibJsonHttpClient, NETWORK_ACCESS_MESSAGE, is_network_access_denied
from .models import ComparisonMethodology, WishlistFailure, WishlistItem, SkipCategory
from .batching import BatchPolicy, CachedBatchPriceService, SteamBatchProvider
from .request_policy import RequestGate, RetryingJsonHttpClient, RetryPolicy
from .steam_access import SteamClient
from .owned_library import LibraryAccessError
from .version import __version__
from .creators import (CREATORS, FEATURED_CREATORS, CreatorCatalogService, CreatorSearchService, featured_by_role,
                       validate_selector, validate_search_query, selector_id)
from .organization_urls import OrganizationHttpClient
from .event_log import (configure_event_logging, runtime_data_directory, emit,
                        job_context, elapsed_ms, error_metadata)

TERMINAL = {"complete", "partial", "cancelled", "failed"}
# TODO: Enable only after authenticated owned-library live QA is complete.
OWNED_LIBRARY_ENABLED = False
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml"),
          "/creators.js": ("creators.js", "text/javascript; charset=utf-8"),
          "/library.js": ("library.js", "text/javascript; charset=utf-8"),
          "/games.js": ("games.js", "text/javascript; charset=utf-8"),
          "/steam-logo.svg": ("steam-logo.svg", "image/svg+xml"),
          "/flags.svg": ("flags.svg", "image/svg+xml")}

EXAMPLE_WISHLIST = (
    WishlistItem("413150", "Stardew Valley"),
    WishlistItem("1145360", "Hades"),
    WishlistItem("1091500", "Cyberpunk 2077"),
    WishlistItem("640820", "Pathfinder: Kingmaker"),
    WishlistItem("1245620", "ELDEN RING"),
    WishlistItem("367520", "Hollow Knight"),
    WishlistItem("292030", "The Witcher 3: Wild Hunt"),
)


class Cancelled(Exception):
    pass


class InputError(ValueError):
    pass


class BusyError(RuntimeError):
    pass


def validate_request(payload):
    required = {"identifier", "regions"}
    allowed = {*required, "home", "order", "offer_basis", "excluded_app_ids", "app_ids", "added_app_ids"}
    if not isinstance(payload, dict) or not required <= set(payload) <= allowed:
        raise InputError("Supply a Steam profile and comparison regions.")
    raw = payload["identifier"]
    if not isinstance(raw, str) or not 1 <= len(raw.strip()) <= 200:
        raise InputError("Enter a SteamID64 or a Steam profile URL.")
    identifier = raw.strip()
    if identifier == "selection" and payload.get("app_ids"):
        pass
    elif identifier.lower() == "example":
        identifier = "example"
    elif not re.fullmatch(r"[0-9]{17}", identifier):
        url = urlsplit(identifier)
        if url.scheme not in {"http", "https"} or url.netloc.lower() not in {
            "steamcommunity.com", "store.steampowered.com"
        } or url.query or url.fragment:
            raise InputError("Use a 17-digit SteamID64 or a Steam profile URL without query parameters.")
        pattern = (r"/(profiles/[0-9]{17}|id/[A-Za-z0-9_-]{1,64})/?"
                   if url.netloc.lower() == "steamcommunity.com" else
                   r"/wishlist/(profiles/[0-9]{17}|id/[A-Za-z0-9_-]{1,64})/?")
        if not re.fullmatch(pattern, url.path):
            raise InputError("Use a Steam /profiles/ or /id/ profile URL.")
    regions = payload["regions"]
    if not isinstance(regions, list) or not 1 <= len(regions) <= MAX_COMPARISONS:
        raise InputError(f"Choose between one and {MAX_COMPARISONS} comparison storefronts.")
    try:
        config = ComparisonConfig.from_regions(regions, home=payload.get("home", "pl"))
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    if not isinstance(payload.get("order", "priority"), str) or payload.get("order", "priority") not in WISHLIST_ORDERS:
        raise InputError("Choose a supported wishlist loading order.")
    if payload.get("offer_basis", "game") not in ("game", "best"):
        raise InputError("Choose game price or Steam's best offer as primary.")
    validate_exclusions(payload.get("excluded_app_ids", []))
    for field in ("app_ids", "added_app_ids"):
        if field in payload:
            ids = payload[field]
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 1000
                    or any(not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", value)
                           or int(value) > 4294967295 for value in ids)
                    or len(set(ids)) != len(ids)):
                raise InputError("Supply 1 to 1,000 unique Steam App IDs.")
    if "app_ids" in payload and not set(payload.get("added_app_ids", [])) <= set(payload["app_ids"]):
        raise InputError("Added games must belong to the selection.")
    return identifier, config


def validate_exclusions(values):
    if (not isinstance(values, list) or len(values) > 10000 or
            any(not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}", value) for value in values) or
            len(set(values)) != len(values)):
        raise InputError("Supply up to 10,000 unique removed product IDs.")
    return values


def rates_to_baseline(rates, currency):
    """NBP quotes PLN per unit; divide both legs for a non-PLN baseline."""
    baseline = rates[currency].rate_to_pln
    return {key: rate.rate_to_pln / baseline for key, rate in rates.items()}


def validate_library_request(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("order", "name"), str) or payload.get("order", "name") not in {"name", "steam"}:
        raise InputError("Choose Name or Steam order for your library.")
    identifier, config = validate_request({**payload, "order": "name" if payload.get("order", "name") == "name" else "priority"})
    if identifier == "example" or "store.steampowered.com" in identifier:
        raise InputError("Use a 17-digit SteamID64 or a Steam community profile URL for your library.")
    return identifier, config


def validate_creator_request(payload):
    if not isinstance(payload, dict) or not {"regions", "mode"} <= payload.keys() or payload.keys() - {"regions", "home", "mode", "creator_id", "start", "app_ids", "selector", "excluded_app_ids", "catalog_memberships"}:
        raise InputError("Supply catalog comparison settings.")
    if not isinstance(payload["mode"], str) or payload["mode"] not in {"featured", "catalog", "products"}:
        raise InputError("Choose featured games or a catalog.")
    regions = payload["regions"]
    if not isinstance(regions, list):
        raise InputError(f"Choose between one and {MAX_COMPARISONS} comparison storefronts.")
    config = ComparisonConfig.from_regions(regions, home=payload.get("home", "pl"))
    validate_exclusions(payload.get("excluded_app_ids", []))
    source = {"mode": payload["mode"]}
    if payload["mode"] == "products":
        app_ids = payload.get("app_ids")
        if (not isinstance(app_ids, list) or not 1 <= len(app_ids) <= 1000 or
                any(not isinstance(app_id, str) or not re.fullmatch(r"[0-9]{1,12}", app_id) for app_id in app_ids) or
                len(set(app_ids)) != len(app_ids) or "creator_id" in payload or "start" in payload):
            raise InputError("Supply up to 1,000 unique product IDs.")
        source["app_ids"] = list(app_ids)
        if "catalog_memberships" in payload:
            memberships = payload["catalog_memberships"]
            if (not isinstance(memberships, dict) or len(memberships) > 20 or
                    any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key)
                        or not isinstance(ids, list) or len(ids) > 1000
                        or any(not isinstance(value, str) for value in ids)
                        or len(set(ids)) != len(ids) or not set(ids) <= set(app_ids)
                        for key, ids in memberships.items())):
                raise InputError("Supply up to 20 catalog memberships from the selected products.")
            source["catalog_memberships"] = deepcopy(memberships)
    elif payload["mode"] == "catalog":
        creator_id, start = payload.get("creator_id"), payload.get("start", 0)
        if "selector" in payload:
            selector = validate_selector(payload["selector"])
            if creator_id != selector_id(selector):
                raise InputError("Creator selection does not match its ID.")
            source["selector"] = selector
        elif not isinstance(creator_id, str) or creator_id not in CREATORS:
            raise InputError("Choose a developer or publisher from search.")
        if isinstance(start, bool) or not isinstance(start, int) or not 0 <= start <= 100_000:
            raise InputError("Invalid catalog page.")
        source.update(creator_id=creator_id, start=start)
    elif "creator_id" in payload or "start" in payload:
        raise InputError("Featured comparisons do not take a catalog page.")
    if payload["mode"] != "products" and "app_ids" in payload:
        raise InputError("This comparison does not take product IDs.")
    if payload["mode"] != "catalog" and "selector" in payload:
        raise InputError("Only catalog comparisons take a creator selection.")
    if "catalog_memberships" in payload and payload["mode"] != "products":
        raise InputError("Only explicit products accept catalog memberships.")
    return config, source


class Job:
    def __init__(self, identifier, config, owner, order, creator_request=None, library=False, offer_basis="game"):
        self.id = secrets.token_urlsafe(24)
        self.token = secrets.token_urlsafe(32)
        self.identifier, self.config, self.owner, self.order = identifier, config, owner, order
        self.creator_request = deepcopy(creator_request)
        self.excluded_app_ids = set()
        self.excluded_catalog_ids = set()
        self.library = library
        self.offer_basis = offer_basis
        self.request_app_ids = None
        self.added_app_ids = ()
        # Private, expiring discovery state; never saved to the shared price cache.
        self.loaded_items = None
        self.creator_membership = {}
        self.catalog_warnings = []
        self.comparison_id = self.id
        self.previous_job_id = None
        self.cancel = threading.Event()
        self.lock = threading.RLock()
        self.updated = time.monotonic()
        self.created = self.updated
        self.data = {"state": "queued", "message": "Queued — waiting for the current comparison.",
                     "profile": identifier, "home": config.home.region, "regions": [r.region for r in config.alternatives], "order": order,
                     "total": 0, "items": [], "rates": [], "warnings": [], "error": None, "offer_basis": offer_basis,
                     "methodology": asdict(ComparisonMethodology(rule="FAIR means the baseline price is no higher than every selected price converted to the baseline currency."))}
        if creator_request:
            self.data.update(profile="", source="creators", creator_request=self.creator_request, catalogs={})
        elif library:
            self.data.update(source="library", order="steam" if order == "priority" else order)

    def update(self, **values):
        with self.lock:
            if "catalogs" in values:
                values["catalogs"] = {key: page for key, page in values["catalogs"].items()
                                      if key not in self.excluded_catalog_ids}
            self.data.update(values)
            self.updated = time.monotonic()

    def append(self, item):
        with self.lock:
            if item["app_id"] in self.excluded_app_ids:
                return
            if self.creator_request and "creator_ids" in item:
                item = {**item, "creator_ids": [key for key in item["creator_ids"] if key not in self.excluded_catalog_ids]}
            self.data["items"].append(item)
            noun = "products" if self.creator_request else "games"
            self.data["message"] = f"Checked {len(self.data['items'])} of {self.data['total']} {noun}"
            self.updated = time.monotonic()

    def snapshot(self):
        with self.lock:
            result = {**self.data, "items": list(self.data["items"]),
                      "rates": list(self.data["rates"]), "warnings": list(self.data["warnings"])}
            if "catalogs" in result:
                result["catalogs"] = deepcopy(result["catalogs"])
                result["creator_request"] = deepcopy(result["creator_request"])
            return result

    def remove_titles(self, app_ids):
        """Forget comparison records, retaining only IDs to reject late worker results.

        Undo lives in the browser for seven seconds; this operation is permanent
        and idempotent. Shared regional price observations are not modified.
        """
        with self.lock:
            removed = set(app_ids)
            if len(removed | self.excluded_app_ids) > 10000:
                raise InputError("This comparison supports up to 10,000 removed product IDs.")
            known = {item["app_id"] for item in self.data["items"]}
            known.update(item.app_id for item in self.loaded_items or ())
            for page in self.data.get("catalogs", {}).values():
                known.update(item["app_id"] for item in page["products"])
                page["products"] = [item for item in page["products"] if item["app_id"] not in removed]
            count = len((removed - self.excluded_app_ids) & known)
            self.excluded_app_ids.update(removed)
            self.data["items"] = [item for item in self.data["items"] if item["app_id"] not in removed]
            if self.loaded_items is not None:
                self.loaded_items = tuple(item for item in self.loaded_items if item.app_id not in removed)
            for app_id in removed:
                self.creator_membership.pop(app_id, None)
            if self.request_app_ids is not None:
                self.request_app_ids = tuple(value for value in self.request_app_ids if value not in removed)
            self.added_app_ids = tuple(value for value in self.added_app_ids if value not in removed)
            if self.creator_request and "app_ids" in self.creator_request:
                self.creator_request["app_ids"] = [app_id for app_id in self.creator_request["app_ids"] if app_id not in removed]
                for key, ids in self.creator_request.get("catalog_memberships", {}).items():
                    self.creator_request["catalog_memberships"][key] = [app_id for app_id in ids if app_id not in removed]
            self.data["total"] = max(0, self.data["total"] - count)
            noun = "products" if self.creator_request else "games"
            self.data["message"] = f"Checked {len(self.data['items'])} of {self.data['total']} {noun}."
            self.updated = time.monotonic()

    def remove_catalogs(self, catalog_ids, orphan_app_ids=()):
        """Drop private catalog state and exclusive products, preserving shared titles."""
        with self.lock:
            removed = set(catalog_ids)
            if len(removed | self.excluded_catalog_ids) > 1000:
                raise InputError("This comparison supports up to 1,000 removed catalogs.")
            memberships = deepcopy(self.creator_membership)
            for key, page in self.data.get("catalogs", {}).items():
                for product in page["products"]:
                    memberships.setdefault(product["app_id"], []).append(key)
            for key, ids in self.creator_request.get("catalog_memberships", {}).items():
                for app_id in ids:
                    memberships.setdefault(app_id, []).append(key)
            excluded = self.excluded_catalog_ids | removed
            retained = {app_id: list(dict.fromkeys(key for key in keys if key not in excluded))
                        for app_id, keys in memberships.items()}
            orphaned = {app_id for app_id, keys in retained.items() if not keys}
            orphaned.update(app_id for app_id in orphan_app_ids if not retained.get(app_id))
            if len(orphaned | self.excluded_app_ids) > 10000:
                raise InputError("This comparison supports up to 10,000 removed product IDs.")
            self.excluded_catalog_ids.update(removed)
            self.creator_membership = {app_id: keys for app_id, keys in retained.items() if keys}
            for key in removed:
                self.data.get("catalogs", {}).pop(key, None)
                self.creator_request.get("catalog_memberships", {}).pop(key, None)
            self.data["items"] = [{**item, "creator_ids": [key for key in item["creator_ids"] if key not in excluded]}
                                  if "creator_ids" in item else item for item in self.data["items"]]
            if self.creator_request.get("creator_id") in excluded:
                self.creator_request.clear()
                self.creator_request.update(mode="products", app_ids=[item.app_id for item in self.loaded_items or () if item.app_id not in orphaned])
            self.remove_titles(orphaned)

    def check_cancelled(self):
        if self.cancel.is_set():
            raise Cancelled()


class CancellableHttpClient:
    def __init__(self, upstream, job):
        self.upstream, self.job = upstream, job

    def get_json(self, url, headers=None):
        self.job.check_cancelled()
        result = self.upstream.get_json(url, headers)
        self.job.check_cancelled()
        return result


class JobManager:
    def __init__(self, data_directory, *, api_key="", max_jobs=20, max_games=1000,
                 runner=None, start_worker=True, batch_policy=BatchPolicy(),
                 max_completed_jobs=100, completed_bytes=32 * 1024 * 1024):
        self.data_directory = Path(data_directory)
        self.api_key = api_key
        self.max_jobs, self.max_games = max_jobs, max_games
        self.batch_policy = batch_policy
        self.max_completed_jobs = max_completed_jobs
        self.completed_bytes = completed_bytes
        self.jobs = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue(maxsize=max_jobs)
        self.gate = RequestGate(1.5)
        self.catalogs = CreatorCatalogService(time.monotonic)
        self.creator_search = CreatorSearchService(time.monotonic)
        self.game_search = GameSearch(time.monotonic)
        self.runner = runner or self._analyze
        self.thread = None
        if start_worker:
            self.thread = threading.Thread(target=self._work, daemon=True, name="wishlist-worker")
            self.thread.start()

    def submit(self, identifier, config, owner, order="priority", creator_request=None, library=False,
               *, source_job=None, excluded_app_ids=(), app_ids=None, added_app_ids=(), offer_basis="game"):
        if order not in WISHLIST_ORDERS:
            raise ValueError(f"Unsupported wishlist order: {order!r}")
        if offer_basis not in ("game", "best"):
            raise ValueError("Invalid primary offer")
        with self.lock:
            now = time.monotonic()
            if source_job is not None:
                if (self.jobs.get(source_job.id) is not source_job or
                        now - source_job.updated >= 3600):
                    raise InputError("This comparison is unavailable or has expired.")
                if source_job.data["state"] not in {"complete", "partial"} or source_job.loaded_items is None:
                    raise BusyError("Wait for the comparison to finish before changing currencies.")
                if any(job.comparison_id == source_job.comparison_id and job.data["state"] not in TERMINAL
                       for job in self.jobs.values()):
                    raise BusyError("A currency change is already running for this comparison.")
                identifier = source_job.data["profile"]
                order, creator_request, library = source_job.order, source_job.creator_request, source_job.library
                offer_basis = source_job.offer_basis
            self.jobs = {key: job for key, job in self.jobs.items()
                         if job.data["state"] not in TERMINAL or now - job.updated < 3600}
            if any(job.owner == owner and job.data["state"] not in TERMINAL for job in self.jobs.values()):
                raise BusyError("A comparison is already running from this connection. Wait for it or cancel it first.")
            self._prune_completed(now)
            if sum(job.data["state"] not in TERMINAL for job in self.jobs.values()) >= self.max_jobs or self.queue.full():
                raise BusyError("The comparison service is busy. Please try again later.")
            job = Job(identifier, config, owner, order, creator_request, library, offer_basis)
            job.request_app_ids = tuple(app_ids) if app_ids is not None else None
            job.added_app_ids = tuple(added_app_ids)
            job.excluded_app_ids.update(excluded_app_ids)
            if source_job is not None:
                with source_job.lock:
                    job.request_app_ids = source_job.request_app_ids
                    job.added_app_ids = source_job.added_app_ids
                    job.loaded_items = source_job.loaded_items
                    job.creator_membership = deepcopy(source_job.creator_membership)
                    job.catalog_warnings = list(source_job.catalog_warnings)
                    job.excluded_app_ids.update(source_job.excluded_app_ids)
                    job.excluded_catalog_ids.update(source_job.excluded_catalog_ids)
                job.comparison_id = source_job.comparison_id
                job.previous_job_id = source_job.id
                job.data.update(previous_job_id=source_job.id, total=len(job.loaded_items),
                                message="Queued — updating comparison currencies.")
                if creator_request:
                    job.data["catalogs"] = deepcopy(source_job.snapshot()["catalogs"])
            self.jobs[job.id] = job
            emit("job_queued", job_id=job.id)
            self.queue.put_nowait(job)
            return job

    def _prune_completed(self, now):
        """Retention never consumes active-work capacity. Caller holds manager lock."""
        total = count = 0
        completed = sorted((job for job in self.jobs.values() if job.data["state"] in TERMINAL),
                           key=lambda job: job.updated, reverse=True)
        for job in completed:
            size = len(json.dumps(job.snapshot(), ensure_ascii=True).encode("utf-8"))
            count += 1
            total += size
            if now - job.updated >= 3600 or count > self.max_completed_jobs or total > self.completed_bytes:
                self.jobs.pop(job.id, None)

    def change_currencies(self, source_job, config, owner):
        """Queue a new comparison of a completed job's exact loaded selection."""
        return self.submit("", config, owner, source_job=source_job)

    def get(self, job_id, token):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token) or not hmac.compare_digest(job.token, token):
                return None
            if job.data["state"] in TERMINAL and time.monotonic() - job.updated >= 3600:
                del self.jobs[job_id]
                return None
            return job

    def cancel_job(self, job):
        job.cancel.set()
        with job.lock:
            if job.data["state"] in TERMINAL:
                return
            job.data["state"] = "cancelling"
            job.data["message"] = "Cancelling — waiting for the current request to finish."
        emit("job_cancel_requested", job_id=job.id)

    def _work(self):
        while True:
            try:
                job = self.queue.get(timeout=60)
            except queue.Empty:
                with self.lock:
                    now = time.monotonic()
                    self.jobs = {key: value for key, value in self.jobs.items()
                                 if value.data["state"] not in TERMINAL or now - value.updated < 3600}
                continue
            try:
                self.execute(job)
            finally:
                self.queue.task_done()

    def execute(self, job):
        with job_context(job.id):
            started = time.monotonic()
            diagnostic = {}
            emit("job_started", queue_wait_ms=(started - job.created) * 1000)
            try:
                job.check_cancelled()
                self.runner(job)
                job.check_cancelled()
            except Cancelled:
                job.update(state="cancelled", message="Comparison cancelled.")
            except Exception as exc:
                diagnostic = error_metadata(exc)
                if is_network_access_denied(exc):
                    job.update(state="failed", error=NETWORK_ACCESS_MESSAGE,
                               error_code="network_access_denied", message="Server network access blocked.")
                else:
                    # Never return exception strings, URLs, API keys, or local paths.
                    job.update(state="failed", error="Could not complete the comparison. Steam or the exchange-rate service may be unavailable. Try again shortly.",
                               message="Comparison could not be completed.")
            finally:
                result = job.snapshot()
                if result["state"] == "failed":
                    diagnostic.setdefault("category", result.get("error_code") or "comparison_failed")
                emit("job_failed" if result["state"] == "failed" else "job_finished",
                     state=result["state"], duration_ms=elapsed_ms(started), total=result["total"],
                     checked=len(result["items"]), **diagnostic)
                job.identifier = ""  # Attribution remains only in the private, expiring result.
                with self.lock:
                    self._prune_completed(time.monotonic())

    def _analyze(self, job):
        with job.lock:
            creator_request = deepcopy(job.creator_request)
        job.update(state="loading", message="Updating comparison currencies…" if job.previous_job_id else
                   "Loading owned library…" if job.library else "Loading catalog products…" if creator_request else "Loading public wishlist…")
        def sleep(seconds):
            if job.cancel.wait(seconds):
                raise Cancelled()
        def client(gate=None):
            return RetryingJsonHttpClient(
                CancellableHttpClient(UrllibJsonHttpClient(timeout=15), job),
                gate=gate, policy=RetryPolicy(max_attempts=3, maximum_delay=15), sleep=sleep)
        # Deliberately no STEAM_COOKIE or wishlist.txt in the web service.
        steam_http = client(self.gate)
        steam = SteamClient(steam_http, request_delay=0, web_api_key=self.api_key)
        creator_membership = {}
        catalog_warnings = []
        if job.previous_job_id is not None:
            wishlist = job.loaded_items
            creator_membership = job.creator_membership
            catalog_warnings = job.catalog_warnings
            if not wishlist:
                job.update(state="complete", message="No loaded products to compare.")
                return
        elif job.request_app_ids is not None:
            wishlist = tuple(WishlistItem(app_id) for app_id in job.request_app_ids)
        elif creator_request:
            job.update(message="Loading catalog…")
            catalogs = {}
            if creator_request["mode"] == "products":
                wishlist = tuple(WishlistItem(app_id) for app_id in creator_request["app_ids"])
                for creator_id, ids in creator_request.get("catalog_memberships", {}).items():
                    for app_id in ids:
                        creator_membership.setdefault(app_id, []).append(creator_id)
            elif creator_request["mode"] == "featured":
                for creator in FEATURED_CREATORS:
                    catalogs[creator.id] = {"products": [asdict(item) for item in creator.examples],
                                           "total": None, "next_start": 0, "has_more": True}
            else:
                creator_id = creator_request["creator_id"]
                creator = (self.creator_search.resolve(client(self.gate), creator_request["selector"], job.config.home.region)
                           if "selector" in creator_request else CREATORS[creator_id])
                page = self.catalogs.get_page(client(self.gate), creator if "selector" in creator_request else creator_id, job.config.home.region,
                                              creator_request["start"])
                catalogs[creator_id] = {**page, "creator": creator.public()}
                if page["source"] == "stale cache":
                    catalog_warnings.append("Steam's catalog could not be refreshed. Showing a cached catalog page.")
            if creator_request["mode"] != "products":
                wishlist = []
                for creator_id, page in catalogs.items():
                    for product in page["products"]:
                        creator_membership.setdefault(product["app_id"], []).append(creator_id)
                        wishlist.append(WishlistItem(product["app_id"], product["name"]))
                wishlist = deduplicate_wishlist(wishlist)
            if len(wishlist) > self.max_games:
                raise InputError("Too many products in this comparison.")
            job.update(catalogs=catalogs)
        elif job.library:
            try:
                library = steam.get_owned_library(job.identifier)
            except LibraryAccessError as exc:
                job.update(state="failed", error=str(exc), error_code=exc.code, message="Library retrieval failed.")
                return
            job.check_cancelled()
            wishlist = deduplicate_wishlist(library.items)
            if len(wishlist) > self.max_games:
                job.update(state="failed", error=f"This version supports up to {self.max_games} owned games per comparison. This library exceeds that limit; no partial library was compared.", error_code="library_limit")
                return
            if not wishlist:
                job.loaded_items = ()
                job.update(state="complete", message="Steam returned an empty library. Free-to-play games are excluded.")
                return
        elif job.identifier == "example":
            wishlist = EXAMPLE_WISHLIST
        else:
            wishlist_result = steam.get_wishlist(job.identifier)
            job.check_cancelled()
            wishlist = deduplicate_wishlist(wishlist_result.items)
            if wishlist_result.failure is not None:
                messages = {
                    WishlistFailure.NETWORK_ACCESS_DENIED: NETWORK_ACCESS_MESSAGE,
                    WishlistFailure.TLS: "The server could not verify its secure connection to Steam. This is a server connection problem, not a wishlist privacy setting.",
                    WishlistFailure.REQUEST: "Steam could not be reached to load your wishlist. Please try again shortly.",
                    WishlistFailure.INVALID_RESPONSE: "Steam returned an unreadable wishlist response. Please try again shortly.",
                    WishlistFailure.VANITY: "Could not resolve that custom profile URL. Try your numeric SteamID64 instead.",
                }
                job.update(state="failed", error=messages[wishlist_result.failure],
                           error_code=wishlist_result.failure.value, message="Wishlist retrieval failed.")
                return
            if not wishlist:
                message = "No public wishlist games were found. Check your profile and wishlist privacy settings."
                if "/id/" in job.identifier and not self.api_key:
                    message += " Try your numeric SteamID64; custom URL resolution is not configured on this server."
                job.update(state="failed", error=message, message="No games to compare.")
                return
            if len(wishlist) > self.max_games:
                job.update(state="failed", error=f"This version supports up to {self.max_games} wishlist games per comparison.")
                return
            if any(not re.fullmatch(r"[0-9]{1,12}", item.app_id) for item in wishlist):
                raise ValueError("Invalid app ID")
            if job.order in STEAM_WISHLIST_ORDERS:
                ordered = steam.get_wishlist_order(job.identifier, wishlist, STEAM_WISHLIST_ORDERS[job.order], job.config.home.region)
                job.check_cancelled()
                if ordered.failure:
                    job.update(state="failed", error=NETWORK_ACCESS_MESSAGE if ordered.failure is WishlistFailure.NETWORK_ACCESS_DENIED
                               else "Steam could not provide the selected loading order. Retry, or choose another order.",
                               error_code=ordered.failure.value, message="Wishlist ordering failed.")
                    return
                wishlist = ordered.items
        if job.previous_job_id is None and job.request_app_ids is None:
            wishlist = deduplicate_wishlist((*wishlist, *(WishlistItem(app_id) for app_id in job.added_app_ids)))
        if len(wishlist) > self.max_games:
            raise InputError("Too many games in this comparison.")
        with job.lock:
            orphaned = {app_id for app_id, ids in creator_membership.items()
                        if ids and not any(key not in job.excluded_catalog_ids for key in ids)}
            job.remove_titles(orphaned)
            wishlist = tuple(item for item in wishlist if item.app_id not in job.excluded_app_ids)
            job.loaded_items = wishlist
            job.data["total"] = len(wishlist)
            job.creator_membership = {key: [catalog for catalog in value if catalog not in job.excluded_catalog_ids]
                                      for key, value in creator_membership.items() if key not in job.excluded_app_ids}
            for page in job.data.get("catalogs", {}).values():
                page["products"] = [item for item in page["products"] if item["app_id"] not in job.excluded_app_ids]
        if not wishlist and job.excluded_app_ids:
            job.update(state="complete", total=0, message="All titles have been removed from this comparison.")
            return
        if creator_request and not wishlist:
            job.loaded_items = ()
            job.catalog_warnings = list(catalog_warnings)
            job.update(state="complete", total=0, warnings=catalog_warnings,
                       message="No individual products found on this catalog page. Try Load more if available, or check the exact name.")
            return
        job.catalog_warnings = list(catalog_warnings)
        job.update(message="Getting exchange rates…")
        cache = SQLiteCache(self.data_directory / "cache.sqlite3")
        rates = CachedExchangeRateProvider(NbpExchangeRateProvider(client()), cache).get_rate_details(tuple(dict.fromkeys((*job.config.currencies, job.config.home.currency))))
        job.check_cancelled()
        warnings = list(catalog_warnings)
        if any(rate.cache_status == "stale cache" for rate in rates.values()):
            warnings.append("Exchange-rate refresh failed. Using stale cached rates; check their publication dates below.")
        rate_rows = []
        checked_at = datetime.now(timezone.utc).isoformat()
        for rate in rates.values():
            row = asdict(rate)
            cached_rate = cache.get_exchange_rate(rate.currency)
            row["checked_at_utc"] = checked_at
            row["retrieved_at_utc"] = (datetime.fromtimestamp(cached_rate.fetched_at, timezone.utc).isoformat()
                                       if cached_rate else None)
            rate_rows.append(row)
        order_messages = {
            "priority": "Comparing games in personal priority order…",
            "date_added": "Comparing newest wishlist additions first…",
            "name": "Loading game names to prepare alphabetical order…",
            "price": "Preparing baseline prices to load the cheapest primary offers first…",
            "discount": "Preparing baseline offers to load the largest discounts first…",
            "top_selling": "Comparing games in Steam's Top Selling order…",
            "release_date": "Comparing games in Steam's Release Date order…",
            "review_score": "Comparing games in Steam's Review Score order…",
        }
        if job.order in STEAM_WISHLIST_ORDERS and (job.request_app_ids is not None or job.identifier == "example"):
            order_messages[job.order] = "Comparing games in saved selection order…"
        job.update(state="running", rates=rate_rows, warnings=warnings,
                   message=("Comparing owned games by name…" if job.order == "name" else "Comparing owned games in Steam order…") if job.library else "Comparing catalog products…" if creator_request else order_messages[job.order])
        runner = AnalysisRunner(CachedBatchPriceService(SteamBatchProvider(steam_http, policy=self.batch_policy, check_cancelled=job.check_cancelled), cache), home=job.config.home, alternatives=job.config.alternatives)
        partial = False
        with cache.connection_scope():
            for progress in runner.run(
                wishlist,
                rates_to_baseline(rates, job.config.home.currency),
                order=job.order,
                preserve_order=job.previous_job_id is not None or (job.request_app_ids is not None and job.order not in {"price", "discount"}),
                offer_basis=job.offer_basis,
            ):
                job.check_cancelled()
                item = asdict(progress)
                item["manually_added"] = progress.app_id in job.added_app_ids
                if creator_request:
                    item["creator_ids"] = creator_membership.get(progress.app_id, [])
                item["source_summary"] = progress.source_summary
                if progress.skipped:
                    # Only controlled labels cross the web boundary; upstream errors
                    # may contain URLs, local information, or unexpected text.
                    item["skipped"]["reason"] = progress.skipped.category.label
                    partial |= progress.skipped.category.is_technical_failure
                job.append(item)
                if progress.skipped and progress.skipped.category is SkipCategory.NETWORK_ACCESS_DENIED:
                    job.update(state="failed", error=NETWORK_ACCESS_MESSAGE,
                               error_code="network_access_denied", message="Server network access blocked.")
                    return
        job.check_cancelled()
        if any(any(offer.get("status") in {"temporary_failure", "request_failure", "invalid_response", "region_mismatch"}
                       for offer in (item.get("best_offers") or {}).values()) for item in job.snapshot()["items"]):
            warnings.append("Some Steam best purchase offers could not be retrieved. Default game comparisons remain available.")
            job.update(warnings=warnings)
        noun = "products" if creator_request else "games"
        # Keep the emitted order even when new country metadata has different names.
        originals = {item.app_id: item for item in wishlist}
        with job.lock:
            job.loaded_items = tuple(originals[item["app_id"]] for item in job.data["items"])
            checked = len(job.loaded_items)
        job.update(state="partial" if partial else "complete", message=f"Checked {checked} {noun}.")


class WebApplication:
    def __init__(self, manager, origin="http://127.0.0.1:8765", asset_directory=None,
                 *, owned_library_enabled=OWNED_LIBRARY_ENABLED):
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("WEB_ORIGIN must be an http(s) origin without a path")
        self.origin = origin.rstrip("/")
        self.host = parsed.netloc
        self.manager = manager
        self.owned_library_enabled = owned_library_enabled
        self.assets = Path(asset_directory or Path(__file__).resolve().parent.parent / "web")

    def __call__(self, environ, start_response):
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        headers = [("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
                   ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://shared.akamai.steamstatic.com https://avatars.fastly.steamstatic.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                   ("Cache-Control", "no-store")]
        def respond(code, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode("utf-8")
            start_response(code, headers + [("Content-Type", content_type), ("Content-Length", str(len(body)))])
            return [body]
        if environ.get("HTTP_HOST", "").lower() != self.host.lower():
            return respond("400 Bad Request", {"error": "Unrecognized host."})
        if path in ASSETS and method in {"GET", "HEAD"}:
            filename, content_type = ASSETS[path]
            content = (self.assets / filename).read_bytes()
            if filename == "index.html":
                content = content.replace(b"{{APP_VERSION}}", __version__.encode("ascii"))
                content = content.replace(b"{{STOREFRONTS}}", escape(json.dumps(dict(STOREFRONTS)), quote=True).encode("utf-8"))
                content = content.replace(b"{{OWNED_LIBRARY_ENABLED}}", b"true" if self.owned_library_enabled else b"false")
                if self.owned_library_enabled:
                    content = content.replace(b'<button id="library-tab" hidden', b'<button id="library-tab"')
            return respond("200 OK", content if method == "GET" else b"", content_type)
        if path == "/api/health" and method == "GET":
            return respond("200 OK", {"status": "ok", "version": __version__})
        if path == "/api/creators" and method == "GET":
            return respond("200 OK", {"creators": [creator.public() for creator in FEATURED_CREATORS],
                                       "developers": [c.public() for c in featured_by_role("developer")],
                                       "publishers": [c.public() for c in featured_by_role("publisher")]})
        if method == "POST":
            if path == "/api/library-jobs" and not self.owned_library_enabled:
                return respond("404 Not Found", {"error": "Owned-library comparisons are not enabled."})
            if environ.get("HTTP_ORIGIN") != self.origin or environ.get("CONTENT_TYPE", "").split(";", 1)[0] != "application/json":
                return respond("403 Forbidden", {"error": "Use this app to submit a comparison."})
            try:
                length = int(environ.get("CONTENT_LENGTH", "0"))
                body_limit = (262144 if path in {"/api/jobs", "/api/creator-jobs"} or path.endswith("/remove")
                              else 8192 if path == "/api/creators/search" else 2048)
                if not 0 < length <= body_limit:
                    raise ValueError()
                payload = json.loads(environ["wsgi.input"].read(length))
            except (ValueError, UnicodeDecodeError):
                return respond("400 Bad Request", {"error": "Invalid request body."})
            if path == "/api/games/search":
                try:
                    if not isinstance(payload, dict) or set(payload) != {"query", "home"} or payload["home"] not in STOREFRONTS:
                        raise ValueError("Supply a game name and supported storefront.")
                    service = self.manager.game_search
                    if not service.lock.acquire(blocking=False):
                        return respond("429 Too Many Requests", {"error": "A game search is in progress. Try again shortly."})
                    try:
                        client = RetryingJsonHttpClient(UrllibJsonHttpClient(timeout=15), gate=self.manager.gate,
                                                       policy=RetryPolicy(max_attempts=2, maximum_delay=5))
                        return respond("200 OK", service.search(client, payload["query"], payload["home"]))
                    finally:
                        service.lock.release()
                except (ValueError, TypeError):
                    return respond("400 Bad Request", {"error": "Enter a game name of 2 to 100 characters and a supported storefront."})
                except HttpClientError as exc:
                    return respond("503 Service Unavailable", {"error": NETWORK_ACCESS_MESSAGE if is_network_access_denied(exc)
                                   else "Steam game search is unavailable. Try again, or enter an App ID."})
            if path == "/api/creators/search":
                try:
                    if not isinstance(payload, dict) or set(payload) not in ({"query", "home"}, {"query", "home", "role"}):
                        raise ValueError("Supply a developer or publisher name and storefront.")
                    role = payload.get("role")
                    if "role" in payload and role not in ("developer", "publisher"):
                        raise ValueError("Choose developers or publishers.")
                    term = validate_search_query(payload["query"])
                    home = payload["home"]
                    if not isinstance(home, str) or home not in STOREFRONTS:
                        raise ValueError("Choose a supported storefront.")
                except ValueError as exc:
                    return respond("400 Bad Request", {"error": str(exc)})
                service = self.manager.creator_search
                if not service.lock.acquire(blocking=False):
                    return respond("429 Too Many Requests", {"error": "A catalog search is in progress. Try again shortly."})
                try:
                    client = RetryingJsonHttpClient(OrganizationHttpClient(timeout=15), gate=self.manager.gate,
                                                     policy=RetryPolicy(max_attempts=2, maximum_delay=5))
                    return respond("200 OK", service.search(client, term, home, role))
                except HttpClientError as exc:
                    return respond("503 Service Unavailable", {"error": NETWORK_ACCESS_MESSAGE if is_network_access_denied(exc)
                                   else "Steam developer/publisher search is unavailable. Please try again shortly."})
                finally:
                    service.lock.release()
            if path in {"/api/jobs", "/api/creator-jobs", "/api/library-jobs"}:
                try:
                    creator_request = None
                    if path == "/api/creator-jobs":
                        config, creator_request = validate_creator_request(payload)
                        identifier = "creators"
                    elif path == "/api/library-jobs":
                        identifier, config = validate_library_request(payload)
                    else:
                        identifier, config = validate_request(payload)
                    job = self.manager.submit(
                        identifier,
                        config,
                        environ.get("REMOTE_ADDR", "unknown"),
                        order=("name" if payload.get("order", "name") == "name" else "priority") if path == "/api/library-jobs" else payload.get("order", "priority"),
                        creator_request=creator_request,
                        library=path == "/api/library-jobs",
                        excluded_app_ids=payload.get("excluded_app_ids", []),
                        app_ids=payload.get("app_ids") if path == "/api/jobs" else None,
                        added_app_ids=payload.get("added_app_ids", []) if path == "/api/jobs" else (),
                        offer_basis=payload.get("offer_basis", "game") if path == "/api/jobs" else "game",
                    )
                except ValueError as exc:
                    return respond("400 Bad Request", {"error": str(exc)})
                except BusyError as exc:
                    return respond("429 Too Many Requests", {"error": str(exc)})
                return respond("202 Accepted", {"id": job.id, "token": job.token})
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]{32})(/cancel|/currencies|/remove|/remove-catalogs)?", path)
        if match and ((method == "GET" and not match[2]) or (method == "POST" and match[2])):
            authorization = environ.get("HTTP_AUTHORIZATION", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            job = self.manager.get(match[1], token)
            if job is None:
                return respond("404 Not Found", {"error": "This comparison is unavailable or has expired."})
            if match[2] == "/remove-catalogs":
                if not job.creator_request:
                    return respond("400 Bad Request", {"error": "Only catalog comparisons support catalog cleanup."})
                try:
                    if (not isinstance(payload, dict) or not {"catalog_ids"} <= payload.keys()
                            or payload.keys() - {"catalog_ids", "app_ids"}):
                        raise InputError("Supply removed catalog IDs.")
                    ids = payload["catalog_ids"]
                    if (not isinstance(ids, list) or not 1 <= len(ids) <= 20
                            or any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key) for key in ids)
                            or len(set(ids)) != len(ids)):
                        raise InputError("Supply 1 to 20 unique catalog IDs.")
                    app_ids = validate_exclusions(payload.get("app_ids", []))
                    if len(app_ids) > 1000:
                        raise InputError("Cleanup accepts up to 1,000 product IDs per request.")
                    job.remove_catalogs(ids, app_ids)
                except ValueError as exc:
                    return respond("400 Bad Request", {"error": str(exc)})
                return respond("200 OK", {"removed_catalogs": ids})
            if match[2] == "/remove":
                if job.library and not self.owned_library_enabled:
                    return respond("404 Not Found", {"error": "Owned-library comparisons are not enabled."})
                try:
                    if not isinstance(payload, dict) or set(payload) != {"app_ids"} or not payload["app_ids"]:
                        raise InputError("Supply removed product IDs.")
                    app_ids = validate_exclusions(payload["app_ids"])
                    job.remove_titles(app_ids)
                except ValueError as exc:
                    return respond("400 Bad Request", {"error": str(exc)})
                return respond("200 OK", {"removed": app_ids})
            if match[2] == "/currencies":
                if job.library and not self.owned_library_enabled:
                    return respond("404 Not Found", {"error": "Owned-library comparisons are not enabled."})
                try:
                    if not isinstance(payload, dict) or not {"regions"} <= payload.keys() <= {"home", "regions"}:
                        raise InputError("Supply a baseline and comparison storefronts.")
                    _, config = validate_request({"identifier": "example", **payload})
                    updated = self.manager.change_currencies(job, config, environ.get("REMOTE_ADDR", "unknown"))
                except ValueError as exc:
                    return respond("400 Bad Request", {"error": str(exc)})
                except BusyError as exc:
                    return respond("429 Too Many Requests", {"error": str(exc)})
                return respond("202 Accepted", {"id": updated.id, "token": updated.token,
                                                 "previous_job_id": job.id})
            if match[2] == "/cancel":
                self.manager.cancel_job(job)
            return respond("200 OK", job.snapshot())
        return respond("404 Not Found", {"error": "Not found."})


def create_app(*, origin=None):
    data = runtime_data_directory()
    configure_event_logging(data)
    return WebApplication(JobManager(data, api_key=os.environ.get("STEAM_WEB_API_KEY", "")),
                          origin=os.environ.get("WEB_ORIGIN", origin or "http://127.0.0.1:8765"))
