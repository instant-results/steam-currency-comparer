"""Steam wishlist and regional-price access."""

from __future__ import annotations

import re
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from urllib.parse import urlencode

from .http_client import HttpClientError, JsonHttpClient, NETWORK_ACCESS_MESSAGE, is_network_access_denied
from .models import (
    RegionalPriceResult,
    SkipCategory,
    StorePrice,
    WishlistItem,
    WishlistFailure,
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


class VanityResolutionStatus(str, Enum):
    NETWORK_ACCESS_DENIED = "network_access_denied"
    RESOLVED = "resolved"
    API_KEY_MISSING = "api_key_missing"
    NOT_FOUND = "not_found"
    REQUEST_FAILED = "request_failed"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class VanityResolution:
    status: VanityResolutionStatus
    steam_id: str | None
    message: str

    @property
    def resolved(self) -> bool:
        return self.status is VanityResolutionStatus.RESOLVED


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
        web_api_key: str = "",
    ) -> None:
        self._http_client = http_client
        self._request_delay = request_delay
        self._sleep = sleep
        self._wishlist_file = wishlist_file
        self._web_api_key = web_api_key.strip()

    def get_owned_library(self, raw_identifier):
        """Get visible owned games in one request; never use cookies/local files."""
        from .owned_library import LibraryAccessError, parse_owned_library, library_request_error
        if not self._web_api_key:
            raise LibraryAccessError("api_key_missing", "Owned libraries require a Steam Web API key. Set STEAM_WEB_API_KEY in the server's launching terminal and restart it. See the usage guide for setup.")
        identifier = normalize_steam_identifier(raw_identifier)
        if not re.fullmatch(r"[0-9]{17}", identifier):
            resolution = self.resolve_vanity_url(identifier)
            if not resolution.resolved:
                code = "network_access_denied" if resolution.status is VanityResolutionStatus.NETWORK_ACCESS_DENIED else "vanity"
                message = NETWORK_ACCESS_MESSAGE if code == "network_access_denied" else "Could not resolve that custom profile URL. Try your numeric SteamID64 instead."
                raise LibraryAccessError(code, message)
            identifier = resolution.steam_id
        query = urlencode({"key": self._web_api_key, "input_json": json.dumps({
            "steamid": identifier, "include_appinfo": True, "include_played_free_games": False,
        })})
        try:
            payload = self._http_client.get_json("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?" + query)
        except HttpClientError as exc:
            raise library_request_error(exc) from exc
        return parse_owned_library(payload)

    def resolve_vanity_url(self, vanity_name: str) -> VanityResolution:
        if not self._web_api_key:
            return VanityResolution(
                VanityResolutionStatus.API_KEY_MISSING,
                None,
                "A Steam Web API key is required to resolve the vanity URL "
                f"'{vanity_name}'. Set STEAM_WEB_API_KEY or use a numeric SteamID64.",
            )

        query = urlencode(
            {
                "key": self._web_api_key,
                "vanityurl": vanity_name,
                "url_type": 1,
            }
        )
        url = (
            "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
            f"?{query}"
        )
        try:
            payload = self._http_client.get_json(url)
        except Exception as exc:
            if is_network_access_denied(exc):
                return VanityResolution(VanityResolutionStatus.NETWORK_ACCESS_DENIED,
                                        None, NETWORK_ACCESS_MESSAGE)
            return VanityResolution(
                VanityResolutionStatus.REQUEST_FAILED,
                None,
                f"The Steam vanity-resolution request failed for '{vanity_name}'.",
            )

        if not isinstance(payload, dict) or not isinstance(
            payload.get("response"), dict
        ):
            return VanityResolution(
                VanityResolutionStatus.INVALID_RESPONSE,
                None,
                f"Steam returned an invalid vanity response for '{vanity_name}'.",
            )

        response = payload["response"]
        if response.get("success") != 1:
            detail = response.get("message")
            suffix = f" Steam says: {detail}" if isinstance(detail, str) else ""
            return VanityResolution(
                VanityResolutionStatus.NOT_FOUND,
                None,
                f"Steam could not find the vanity profile '{vanity_name}'.{suffix}",
            )

        steam_id = response.get("steamid")
        if not isinstance(steam_id, str) or not re.fullmatch(r"\d+", steam_id):
            return VanityResolution(
                VanityResolutionStatus.INVALID_RESPONSE,
                None,
                f"Steam returned an invalid SteamID for '{vanity_name}'.",
            )
        return VanityResolution(
            VanityResolutionStatus.RESOLVED,
            steam_id,
            f"Resolved vanity profile '{vanity_name}' to SteamID64 {steam_id}.",
        )

    def get_wishlist(self, raw_identifier: str) -> WishlistResult:
        identifier = normalize_steam_identifier(raw_identifier)
        warnings: list[str] = []
        lookup_identifier: str | None = identifier
        failure = None

        if not re.fullmatch(r"\d+", identifier):
            resolution = self.resolve_vanity_url(identifier)
            if resolution.status is VanityResolutionStatus.NETWORK_ACCESS_DENIED:
                return WishlistResult((), "Steam Web API", (resolution.message,),
                                      WishlistFailure.NETWORK_ACCESS_DENIED)
            if resolution.resolved:
                lookup_identifier = resolution.steam_id
            else:
                lookup_identifier = None
                warnings.append(resolution.message)
                failure = WishlistFailure.VANITY

        if lookup_identifier is not None:
            api_url = (
                "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
                f"?{urlencode({'steamid': lookup_identifier})}"
            )
            try:
                payload = self._http_client.get_json(api_url)
                if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
                    raise ValueError("Invalid wishlist response")
                raw_items = payload["response"].get("items", [])
                if not isinstance(raw_items, list) or any(
                    not isinstance(item, dict) or isinstance(item.get("appid"), bool)
                    or not re.fullmatch(r"[0-9]{1,12}", str(item.get("appid", "")))
                    for item in raw_items
                ):
                    raise ValueError("Invalid wishlist items")
                items = tuple(
                    WishlistItem(
                        str(item["appid"]),
                        date_added=self._optional_nonnegative_int(item.get("date_added")),
                        priority=self._optional_nonnegative_int(item.get("priority")),
                    )
                    for item in raw_items
                )
                return WishlistResult(items, "Steam Web API", tuple(warnings))
            except HttpClientError as exc:
                if exc.network_access_denied:
                    local_items = self._load_local_wishlist()
                    return WishlistResult(local_items, "wishlist.txt" if local_items else "Steam Web API",
                                          (NETWORK_ACCESS_MESSAGE,),
                                          None if local_items else WishlistFailure.NETWORK_ACCESS_DENIED)
                failure = (WishlistFailure.TLS if exc.tls_error else
                           WishlistFailure.INVALID_RESPONSE if exc.invalid_response else WishlistFailure.REQUEST)
                warnings.append("Steam Web API wishlist retrieval failed.")
            except (ValueError, TypeError):
                failure = WishlistFailure.INVALID_RESPONSE
                warnings.append("Steam returned an invalid wishlist response.")

        local_items = self._load_local_wishlist()
        if local_items:
            return WishlistResult(local_items, "wishlist.txt", tuple(warnings))

        legacy_items, legacy_failure = self._get_legacy_wishlist(lookup_identifier or identifier, warnings)
        if legacy_failure is WishlistFailure.NETWORK_ACCESS_DENIED:
            failure = legacy_failure
        return WishlistResult(legacy_items, "legacy Steam store endpoint", tuple(warnings),
                              (failure or legacy_failure) if not legacy_items else legacy_failure)

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
    ) -> tuple[tuple[WishlistItem, ...], WishlistFailure | None]:
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
            except HttpClientError as exc:
                warnings.append("Legacy Steam wishlist retrieval failed.")
                if exc.network_access_denied:
                    return (), WishlistFailure.NETWORK_ACCESS_DENIED
                failure = WishlistFailure.TLS if exc.tls_error else WishlistFailure.REQUEST
                return (), failure
            if not isinstance(payload, dict) or any(
                not re.fullmatch(r"[0-9]{1,12}", str(app_id)) or not isinstance(details, dict)
                or ("name" in details and not isinstance(details["name"], str))
                for app_id, details in payload.items()
            ):
                warnings.append("Steam returned an invalid legacy wishlist response.")
                return (), WishlistFailure.INVALID_RESPONSE
            if not payload:
                break
            page_items = tuple(
                WishlistItem(
                    str(app_id),
                    details.get("name", f"App {app_id}"),
                    date_added=self._optional_nonnegative_int(details.get("date_added")),
                    priority=self._optional_nonnegative_int(details.get("priority")),
                )
                for app_id, details in payload.items()
            )
            items.extend(page_items)
            if len(page_items) < 50:
                break
            page += 1
            if page >= 100:
                warnings.append("Steam wishlist pagination exceeded the supported limit.")
                return (), WishlistFailure.INVALID_RESPONSE
            self._sleep(0.5)
        return tuple(items), None

    @staticmethod
    def _optional_nonnegative_int(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

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
                "filters": "price_overview,basic,developers,publishers",
            }
        )
        url = f"https://store.steampowered.com/api/appdetails?{query}"
        self._sleep(self._request_delay)

        try:
            response = self._http_client.get_json(url)
        except HttpClientError as exc:
            if exc.network_access_denied:
                raise SteamAccessError(
                    NETWORK_ACCESS_MESSAGE, category=SkipCategory.NETWORK_ACCESS_DENIED,
                    app_id=app_id, region=region, retryable=False,
                ) from exc
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
        def credits(key):
            values = data.get(key)
            return tuple(dict.fromkeys(value.strip() for value in values
                         if isinstance(value, str) and value.strip())) if isinstance(values, list) else ()
        metadata = {"developers": credits("developers"), "publishers": credits("publishers")}
        if data.get("is_free") is True:
            return replace(RegionalPriceResult.no_regional_price(game_name, "Free product", is_free=True), **metadata)
        price_overview = data.get("price_overview")
        if price_overview is None:
            return replace(RegionalPriceResult.no_regional_price(
                game_name,
                f"Steam supplied no regional price for {region}.",
                is_free=False,
            ), **metadata)
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
        initial = price_overview.get("initial")
        discount = price_overview.get("discount_percent")
        # Missing metadata stays unknown rather than being treated as no sale.
        if initial is not None and (
            isinstance(initial, bool) or not isinstance(initial, (int, float))
            or not math.isfinite(initial) or initial < final_cents
        ):
            raise SteamProtocolError("Steam returned an invalid base price.", app_id=app_id, region=region)
        if discount is not None and (
            isinstance(discount, bool) or not isinstance(discount, int) or not 0 <= discount <= 100
        ):
            raise SteamProtocolError("Steam returned an invalid discount percentage.", app_id=app_id, region=region)
        price = StorePrice(region, expected, amount,
                           float(initial) / 100 if initial is not None else None, discount)
        return replace(RegionalPriceResult.available(price, game_name), **metadata)
