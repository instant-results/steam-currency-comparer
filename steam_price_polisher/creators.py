"""Featured Steam creators and defensive parsing of their public catalog pages."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode

from .http_client import HttpClientError, is_network_access_denied
from .models import WishlistItem

CATALOG_PAGE_SIZE = 12
CATALOG_CACHE_TTL = 6 * 3600


@dataclass(frozen=True)
class Creator:
    id: str
    name: str
    role: str
    clan_id: str
    homepage: str
    icon: str
    examples: tuple[WishlistItem, ...]

    def public(self):
        return asdict(self)


FEATURED_CREATORS = (
    Creator("supergiant", "Supergiant Games", "Developer & publisher", "3584665",
            "https://store.steampowered.com/developer/supergiantgames/",
            "https://avatars.fastly.steamstatic.com/a2ac03c229b9dd346495c1efdd7e7c37f910a22f_full.jpg",
            (WishlistItem("1145360", "Hades"), WishlistItem("237930", "Transistor"),
             WishlistItem("107100", "Bastion"))),
    Creator("cdpr", "CD PROJEKT RED", "Developer & publisher", "32989758",
            "https://store.steampowered.com/developer/CDPR/",
            "https://avatars.fastly.steamstatic.com/e50b2b2519ed8315081c51fbfa6b896998f4d81a_full.jpg",
            (WishlistItem("1091500", "Cyberpunk 2077"), WishlistItem("292030", "The Witcher 3: Wild Hunt"),
             WishlistItem("20920", "The Witcher 2: Assassins of Kings"))),
    Creator("devolver", "Devolver Digital", "Publisher", "6638525",
            "https://store.steampowered.com/developer/DevolverDigital/",
            "https://avatars.fastly.steamstatic.com/f25857f17e2a956399e80c6bbc2a577214c5a0ea_full.jpg",
            (WishlistItem("1313140", "Cult of the Lamb"), WishlistItem("460950", "Katana ZERO"),
             WishlistItem("311690", "Enter the Gungeon"))),
)
CREATORS = {creator.id: creator for creator in FEATURED_CREATORS}


class CatalogParser(HTMLParser):
    """Extract product IDs and image labels; never forward Steam HTML to clients."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.products = {}
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.current = None
            app_id = attrs.get("data-ds-appid", "")
            if "store_capsule" in attrs.get("class", "").split() and app_id.isascii() and app_id.isdigit() and len(app_id) <= 12:
                self.current = app_id
                self.products.setdefault(app_id, WishlistItem(app_id))
        elif tag == "img" and self.current and attrs.get("alt", "").strip():
            self.products[self.current] = WishlistItem(self.current, attrs["alt"].strip()[:500])

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Invalid catalog pagination")
    if isinstance(value, str) and (not value.isascii() or not value.isdigit()):
        raise ValueError("Invalid catalog pagination")
    result = int(value)
    if not 0 <= result <= 100_000:
        raise ValueError("Invalid catalog pagination")
    return result


def parse_catalog(payload, start, count=CATALOG_PAGE_SIZE):
    try:
        if not isinstance(payload, dict) or payload.get("success") not in (1, True):
            raise ValueError("Catalog unavailable")
        total, offset, size = (_integer(payload.get(key)) for key in ("total_count", "start", "pagesize"))
        html = payload.get("results_html")
        if offset != start or not 1 <= size <= count or not isinstance(html, str) or len(html) > 2_000_000:
            raise ValueError("Invalid catalog response")
        parser = CatalogParser()
        parser.feed(html)
        products = tuple(parser.products.values())
        if len(products) > count or (start < total and not products):
            raise ValueError("Catalog products missing")
        return {"products": [asdict(item) for item in products], "total": total,
                "next_start": start + size, "has_more": start + size < total}
    except (ValueError, TypeError) as exc:
        raise HttpClientError("Steam returned an unreadable creator catalog.", invalid_response=True) from exc


class CreatorCatalogService:
    """Worker-owned, bounded page cache; regional price caching stays separate."""
    def __init__(self, clock):
        self.clock = clock
        self.pages = {}

    def get_page(self, http_client, creator_id, region, start):
        creator = CREATORS[creator_id]
        key = (creator_id, region, start)
        cached = self.pages.get(key)
        if cached and self.clock() - cached[0] < CATALOG_CACHE_TTL:
            return {**cached[1], "source": "cache"}
        query = urlencode({"start": start, "count": CATALOG_PAGE_SIZE, "cc": region.upper(), "l": "english"})
        url = f"https://store.steampowered.com/curator/{creator.clan_id}/ajaxgetfilteredrecommendations/?{query}"
        try:
            page = parse_catalog(http_client.get_json(url), start)
        except HttpClientError as exc:
            if cached and not is_network_access_denied(exc):
                return {**cached[1], "source": "stale cache"}
            raise
        if len(self.pages) >= 128:
            self.pages.pop(next(iter(self.pages)))
        self.pages[key] = (self.clock(), page)
        return {**page, "source": "live"}
