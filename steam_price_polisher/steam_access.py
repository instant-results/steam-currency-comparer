"""Steam wishlist and regional-price access."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from .http_client import JsonHttpClient
from .models import RegionalPriceResult, StorePrice, WishlistItem, WishlistResult


class SteamAccessError(RuntimeError):
    """Raised when Steam cannot provide data required by the application."""


def normalize_steam_identifier(value: str) -> str:
    """Extract a numeric ID or vanity name from supported Steam URLs."""
    identifier = value.strip().rstrip("/")
    markers = (
        "steamcommunity.com/profiles/",
        "steamcommunity.com/id/",
        "store.steampowered.com/wishlist/profiles/",
        "store.steampowered.com/wishlist/id/",
    )
    for marker in markers:
        if marker in identifier:
            identifier = identifier.split(marker, 1)[1]
            break
    return identifier.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]


class SteamClient:
    def __init__(
        self,
        http_client: JsonHttpClient,
        *,
        request_delay: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
        wishlist_file: Path | None = None,
    ) -> None:
        self._http_client = http_client
        self._request_delay = request_delay
        self._sleep = sleep
        self._wishlist_file = wishlist_file

    def resolve_vanity_url(self, vanity_name: str) -> str | None:
        query = urlencode({"vanityurl": vanity_name, "key": "DUMMY"})
        url = (
            "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
            f"?{query}"
        )
        try:
            payload = self._http_client.get_json(url)
        except Exception:
            return None
        response = payload.get("response", {}) if isinstance(payload, dict) else {}
        if response.get("success") == 1:
            return str(response["steamid"])
        return None

    def get_wishlist(self, raw_identifier: str) -> WishlistResult:
        identifier = normalize_steam_identifier(raw_identifier)
        warnings: list[str] = []
        lookup_identifier = identifier

        if not re.fullmatch(r"\d+", identifier):
            resolved = self.resolve_vanity_url(identifier)
            if resolved:
                lookup_identifier = resolved
            else:
                warnings.append(
                    f"Could not resolve vanity URL '{identifier}' to a numeric Steam ID."
                )

        api_url = (
            "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
            f"?{urlencode({'steamid': lookup_identifier})}"
        )
        try:
            payload = self._http_client.get_json(api_url)
            if isinstance(payload, dict) and "response" in payload:
                raw_items = payload["response"].get("items", [])
                items = tuple(
                    WishlistItem(str(item["appid"]))
                    for item in raw_items
                    if item.get("appid") is not None
                )
                return WishlistResult(items, "Steam Web API", tuple(warnings))
        except Exception as exc:
            warnings.append(f"Steam Web API wishlist request failed: {exc}")

        local_items = self._load_local_wishlist()
        if local_items:
            return WishlistResult(local_items, "wishlist.txt", tuple(warnings))

        legacy_items = self._get_legacy_wishlist(identifier, warnings)
        return WishlistResult(legacy_items, "legacy Steam store endpoint", tuple(warnings))

    def _load_local_wishlist(self) -> tuple[WishlistItem, ...]:
        if self._wishlist_file is None or not self._wishlist_file.exists():
            return ()

        items: list[WishlistItem] = []
        with self._wishlist_file.open("r", encoding="utf-8") as wishlist:
            for raw_line in wishlist:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "," in line:
                    app_id, name = line.split(",", 1)
                    items.append(WishlistItem(app_id.strip(), name.strip()))
                else:
                    items.append(WishlistItem(line, f"App {line}"))
        return tuple(items)

    def _get_legacy_wishlist(
        self,
        identifier: str,
        warnings: list[str],
    ) -> tuple[WishlistItem, ...]:
        path_type = "profiles" if re.fullmatch(r"\d+", identifier) else "id"
        items: list[WishlistItem] = []
        page = 0
        while True:
            url = (
                "https://store.steampowered.com/wishlist/"
                f"{path_type}/{identifier}/wishlistdata/?p={page}"
            )
            try:
                payload = self._http_client.get_json(url)
            except Exception as exc:
                warnings.append(f"Legacy Steam wishlist request failed: {exc}")
                break
            if not isinstance(payload, dict) or not payload:
                break

            page_items = tuple(
                WishlistItem(str(app_id), details.get("name", f"App {app_id}"))
                for app_id, details in payload.items()
            )
            items.extend(page_items)
            if len(page_items) < 50:
                break
            page += 1
            self._sleep(0.5)
        return tuple(items)

    def get_regional_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
    ) -> RegionalPriceResult:
        query = urlencode(
            {
                "appids": app_id,
                "cc": region,
                "filters": "price_overview,basic",
            }
        )
        url = f"https://store.steampowered.com/api/appdetails?{query}"
        self._sleep(self._request_delay)

        try:
            response = self._http_client.get_json(url)
        except Exception as exc:
            raise SteamAccessError(
                f"Regional price request failed for app {app_id} ({region}): {exc}"
            ) from exc

        app_data = response.get(str(app_id)) if isinstance(response, dict) else None
        if not app_data or not app_data.get("success"):
            return RegionalPriceResult(None, None)

        data = app_data.get("data") or {}
        game_name = data.get("name")
        price_overview = data.get("price_overview")
        if not price_overview or price_overview.get("final") is None:
            return RegionalPriceResult(None, game_name)

        amount = float(price_overview["final"]) / 100.0
        price = StorePrice(region, expected_currency.upper(), amount)
        return RegionalPriceResult(price, game_name)
