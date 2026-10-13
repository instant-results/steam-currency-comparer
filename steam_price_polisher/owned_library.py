"""Strict parsing of Steam's credentialed owned-games response."""
from dataclasses import dataclass

from .models import WishlistItem
from .http_client import HttpClientError, NETWORK_ACCESS_MESSAGE


class LibraryAccessError(ValueError):
    """A controlled, credential-free message safe to show in a private job."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OwnedLibrary:
    items: tuple[WishlistItem, ...]


def parse_owned_library(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
        raise LibraryAccessError("invalid_response", "Steam returned an unreadable owned-library response. Please try again shortly.")
    response = payload["response"]
    if not response:
        raise LibraryAccessError("library_unavailable", "Steam did not expose this library. Check the profile and set Game details to Public. A private or unavailable library cannot be compared.")
    count = response.get("game_count")
    games = response.get("games", [] if count == 0 else None)
    if (isinstance(count, bool) or not isinstance(count, int) or count < 0
            or not isinstance(games, list) or len(games) != count):
        raise LibraryAccessError("invalid_response", "Steam returned an incomplete owned-library response. Please try again shortly.")
    items = []
    for game in games:
        if (not isinstance(game, dict) or isinstance(game.get("appid"), bool)
                or not isinstance(game.get("appid"), int) or not 0 < game["appid"] < 10**12
                or ("name" in game and not isinstance(game["name"], str))):
            raise LibraryAccessError("invalid_response", "Steam returned invalid owned-library game details. Please try again shortly.")
        items.append(WishlistItem(str(game["appid"]), game.get("name") or None))
    return OwnedLibrary(tuple(items))


def library_request_error(error: HttpClientError):
    if error.network_access_denied:
        return LibraryAccessError("network_access_denied", NETWORK_ACCESS_MESSAGE)
    if error.status_code in {401, 403}:
        return LibraryAccessError("api_key_rejected", "Steam rejected the server's Web API key. Check STEAM_WEB_API_KEY and restart the server.")
    if error.tls_error:
        return LibraryAccessError("tls", "The server could not verify its secure connection to Steam. This is a server connection problem.")
    if error.invalid_response:
        return LibraryAccessError("invalid_response", "Steam returned an unreadable owned-library response. Please try again shortly.")
    return LibraryAccessError("request", "Steam could not be reached to load your library. Please try again shortly.")
