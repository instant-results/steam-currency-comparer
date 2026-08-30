"""Steam wishlist and regional-price access."""

from __future__ import annotations

import re
import math
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from .http_client import HttpClientError, JsonHttpClient
from .models import (
    RegionalPriceResult,
    SkipCategory,
    StorePrice,
    WishlistItem,
    WishlistResult,
)


class SteamAccessError(RuntimeError):
    """Raised when Steam cannot provide data required by the application."""

    def __init__(
        self,
        message: str,
        *,
        category: SkipCategory,
        app_id: str,
        region: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.app_id = str(app_id)
        self.region = region
        self.retryable = retryable


class SteamTemporaryError(SteamAccessError):
    def __init__(self, message: str, *, app_id: str, region: str) -> None:
        super().__init__(
            message,
            category=SkipCategory.TEMPORARY_FAILURE,
            app_id=app_id,
            region=region,
            retryable=True,
        )


class SteamProtocolError(SteamAccessError):
    def __init__(self, message: str, *, app_id: str, region: str) -> None:
        super().__init__(
            message,
            category=SkipCategory.INVALID_RESPONSE,
            app_id=app_id,
            region=region,
            retryable=False,
        )


class SteamRegionMismatchError(SteamAccessError):
    def __init__(self, message: str, *, app_id: str, region: str) -> None:
        super().__init__(
            message,
            category=SkipCategory.REGION_MISMATCH,
            app_id=app_id,
            region=region,
            retryable=False,
        )


class SteamRequestError(SteamAccessError):
    def __init__(self, message: str, *, app_id: str, region: str) -> None:
        super().__init__(
            message,
            category=SkipCategory.REQUEST_FAILURE,
            app_id=app_id,
            region=region,
            retryable=False,
        )


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
        except HttpClientError as exc:
            message = f"Regional request failed for app {app_id} ({region}): {exc}"
            if exc.invalid_response:
                raise SteamProtocolError(
                    message,
                    app_id=app_id,
                    region=region,
                ) from exc
            if exc.transient:
                raise SteamTemporaryError(
                    message,
                    app_id=app_id,
                    region=region,
                ) from exc
            raise SteamRequestError(
                message,
                app_id=app_id,
                region=region,
            ) from exc

        if not isinstance(response, dict):
            raise SteamProtocolError(
                f"Steam returned a non-object response for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )
        if str(app_id) not in response:
            raise SteamProtocolError(
                f"Steam response omitted app {app_id} for region {region}.",
                app_id=app_id,
                region=region,
            )

        app_data = response[str(app_id)]
        if not isinstance(app_data, dict) or "success" not in app_data:
            raise SteamProtocolError(
                f"Steam returned malformed app data for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )
        if app_data["success"] is False:
            return RegionalPriceResult.app_unavailable(
                f"Steam marked app {app_id} unavailable in region {region}."
            )
        if app_data["success"] is not True:
            raise SteamProtocolError(
                f"Steam returned an invalid success flag for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )

        data = app_data.get("data")
        if not isinstance(data, dict):
            raise SteamProtocolError(
                f"Steam returned invalid data for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )
        game_name = data.get("name")
        if game_name is not None and not isinstance(game_name, str):
            raise SteamProtocolError(
                f"Steam returned an invalid game name for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )
        price_overview = data.get("price_overview")
        if price_overview is None:
            return RegionalPriceResult.no_regional_price(
                game_name,
                f"Steam supplied no regional price for {region}.",
            )
        if not isinstance(price_overview, dict):
            raise SteamProtocolError(
                f"Steam returned invalid price data for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )

        final_cents = price_overview.get("final")
        if (
            isinstance(final_cents, bool)
            or not isinstance(final_cents, (int, float))
            or not math.isfinite(final_cents)
            or final_cents < 0
        ):
            raise SteamProtocolError(
                f"Steam returned an invalid final price for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )

        returned_currency = price_overview.get("currency")
        if not isinstance(returned_currency, str) or not returned_currency:
            raise SteamProtocolError(
                f"Steam omitted the price currency for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )
        expected = expected_currency.upper()
        if returned_currency.upper() != expected:
            raise SteamRegionMismatchError(
                f"Steam returned {returned_currency.upper()} instead of {expected} "
                f"for app {app_id} ({region}).",
                app_id=app_id,
                region=region,
            )

        amount = float(final_cents) / 100.0
        price = StorePrice(region, expected, amount)
        return RegionalPriceResult.available(price, game_name)
