"""Featured Steam creators and defensive parsing of their public catalog pages."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
import threading
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
    selector: dict | None = None

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

# Examples are selected independently by role, rather than including every
# self-publishing developer in the publisher tab. The legacy registry stays compatible.
FEATURED_DEVELOPERS = (
    FEATURED_CREATORS[0], FEATURED_CREATORS[1],
    Creator("techland", "Techland", "Developer", "",
            "https://store.steampowered.com/developer/Techland/",
            "https://avatars.fastly.steamstatic.com/009ddefda0c89fb7009af91bd1d92791d257d372_full.jpg",
            (WishlistItem("239140", "Dying Light"),
             WishlistItem("534380", "Dying Light 2 Stay Human: Reloaded Edition"),
             WishlistItem("204450", "Call of Juarez: Gunslinger"))),
)
FEATURED_PUBLISHERS = (
    FEATURED_CREATORS[2],
    Creator("thq-nordic", "THQ Nordic", "Publisher", "",
            "https://store.steampowered.com/publisher/THQNordic/",
            "https://avatars.fastly.steamstatic.com/60cefdca3dddffcd8acabf489140d19c0033b88c_full.jpg",
            (WishlistItem("228380", "Wreckfest"), WishlistItem("610370", "Desperados III"),
             WishlistItem("1084160", "Jagged Alliance 3"))),
    Creator("11-bit", "11 bit studios", "Publisher", "",
            "https://store.steampowered.com/developer/11bitstudios/",
            "https://avatars.fastly.steamstatic.com/ec8f3d00d38cbdf1a6e10ee881e89bfaa0739bba_full.jpg",
            (WishlistItem("606150", "Moonlighter"), WishlistItem("330020", "Children of Morta"),
             WishlistItem("731040", "The Invincible"))),
)


class CatalogParser(HTMLParser):
    """Extract product IDs and image labels; never forward Steam HTML to clients."""
    def __init__(self, search=False):
        super().__init__(convert_charrefs=True)
        self.products = {}
        self.current = None
        self.search = search
        self.in_title = False
        self.title = ""
        self.rows = 0
        self.invalid_rows = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.current = None
            self.in_title = False
            app_id = attrs.get("data-ds-appid", "")
            wanted = "search_result_row" if self.search else "store_capsule"
            if wanted in attrs.get("class", "").split():
                self.rows += 1
                if self.search and re.match(r"https://store\.steampowered\.com/(?:sub|bundle)/[0-9]+/", attrs.get("href", "")):
                    return
            if wanted in attrs.get("class", "").split() and app_id.isascii() and app_id.isdigit() and len(app_id) <= 12:
                self.current = app_id
                self.products.setdefault(app_id, WishlistItem(app_id))
            elif wanted in attrs.get("class", "").split():
                self.invalid_rows |= not (self.search and re.match(
                    r"https://store\.steampowered\.com/(?:sub|bundle)/[0-9]+/", attrs.get("href", "")))
        elif tag == "span" and self.search and self.current and "title" in attrs.get("class", "").split():
            self.in_title = True
            self.title = ""
        elif tag == "img" and self.current and attrs.get("alt", "").strip():
            self.products[self.current] = WishlistItem(self.current, attrs["alt"].strip()[:500])

    def handle_endtag(self, tag):
        if tag == "span" and self.in_title:
            self.products[self.current] = WishlistItem(self.current, self.title.strip()[:500])
            self.in_title = False
        if tag == "a":
            self.current = None
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Invalid catalog pagination")
    if isinstance(value, str) and (not value.isascii() or not value.isdigit()):
        raise ValueError("Invalid catalog pagination")
    result = int(value)
    if not 0 <= result <= 100_000:
        raise ValueError("Invalid catalog pagination")
    return result


def parse_catalog(payload, start, count=CATALOG_PAGE_SIZE, *, search=False):
    try:
        if not isinstance(payload, dict) or payload.get("success") not in (1, True):
            raise ValueError("Catalog unavailable")
        total = _integer(payload.get("total_count"))
        # Steam search uses -1 for an empty result set, even when start=0 was requested.
        offset = start if search and total == 0 and payload.get("start") == -1 else _integer(payload.get("start"))
        size = count if search else _integer(payload.get("pagesize"))
        html = payload.get("results_html")
        if offset != start or not 1 <= size <= count or not isinstance(html, str) or len(html) > 2_000_000:
            raise ValueError("Invalid catalog response")
        parser = CatalogParser(search=search)
        parser.feed(html)
        products = tuple(parser.products.values())
        limit = 50 if search else count
        if parser.invalid_rows or parser.rows > limit or len(products) > limit or (start < total and not parser.rows) or (not search and start < total and not products):
            raise ValueError("Catalog products missing")
        # Steam search may ignore count and return its default 25 rows. Advance
        # through every returned slot, including skipped bundles/packages.
        if search:
            size = max(count, parser.rows)
        return {"products": [asdict(item) for item in products], "total": total,
                "next_start": start + size, "has_more": start + size < total}
    except (ValueError, TypeError) as exc:
        raise HttpClientError("Steam returned an unreadable catalog.", invalid_response=True) from exc


class CreatorCatalogService:
    """Worker-owned, bounded page cache; regional price caching stays separate."""
    def __init__(self, clock):
        self.clock = clock
        self.pages = {}

    def get_page(self, http_client, creator_id, region, start):
        creator = CREATORS[creator_id] if isinstance(creator_id, str) else creator_id
        key = (creator.id, region, start)
        cached = self.pages.get(key)
        if cached and self.clock() - cached[0] < CATALOG_CACHE_TTL:
            return {**cached[1], "source": "cache"}
        query = urlencode({"start": start, "count": CATALOG_PAGE_SIZE, "cc": region.upper(), "l": "english"})
        url = f"https://store.steampowered.com/curator/{creator.clan_id}/ajaxgetfilteredrecommendations/?{query}"
        search = bool(creator.selector and creator.selector["kind"] != "homepage")
        if search:
            query = urlencode({creator.selector["kind"]: creator.name, "start": start,
                               "count": CATALOG_PAGE_SIZE, "cc": region.upper(), "l": "english",
                               "json": 1, "ignore_preferences": 1, "infinite": 1})
            url = f"https://store.steampowered.com/search/results/?{query}"
        try:
            page = parse_catalog(http_client.get_json(url), start, search=search)
        except HttpClientError as exc:
            if cached and not is_network_access_denied(exc):
                return {**cached[1], "source": "stale cache"}
            raise
        if len(self.pages) >= 128:
            self.pages.pop(next(iter(self.pages)))
        self.pages[key] = (self.clock(), page)
        return {**page, "source": "live"}


def validate_selector(value):
    if not isinstance(value, dict):
        raise ValueError("Choose a developer or publisher search result.")
    kind = value.get("kind")
    if kind == "homepage" and set(value) == {"kind", "clan_id"}:
        clan = value["clan_id"]
        if isinstance(clan, str) and re.fullmatch(r"[1-9][0-9]{0,9}", clan) and int(clan) <= 4294967295:
            return {"kind": kind, "clan_id": clan}
    if kind in ("developer", "publisher") and set(value) == {"kind", "name"}:
        return {"kind": kind, "name": validate_search_term(value["name"])}
    raise ValueError("Choose a valid developer or publisher.")


def validate_search_term(value):
    if (not isinstance(value, str) or not 2 <= len(value.strip()) <= 100
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError("Enter a developer or publisher name between 2 and 100 characters.")
    return value.strip()


def selector_id(selector):
    if selector["kind"] == "homepage":
        return "steam-" + selector["clan_id"]
    digest = hashlib.sha256(selector["name"].encode("utf-8")).hexdigest()[:24]
    return selector["kind"] + "-" + digest


def credit_creator(selector):
    return Creator(selector_id(selector), selector["name"], selector["kind"].title(),
                   "", "https://store.steampowered.com/search/?" + urlencode({selector["kind"]: selector["name"]}),
                   "", (), selector)


def featured_by_role(kind):
    """Curated starting games; expansion follows the selected attribution role."""
    featured = {"developer": FEATURED_DEVELOPERS, "publisher": FEATURED_PUBLISHERS}[kind]
    return [replace(credit_creator({"kind": kind, "name": creator.name}),
                    icon=creator.icon, examples=creator.examples)
            for creator in featured]


def _api_url(method, payload):
    return "https://api.steampowered.com/" + method + "/v1/?" + urlencode({"input_json": json.dumps(payload)})


def _store_items(payload):
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        raise HttpClientError("Steam returned an unreadable catalog search.", invalid_response=True)
    items = response.get("store_items", [])
    if not isinstance(items, list) or len(items) > 50:
        raise HttpClientError("Steam returned an unreadable catalog search.", invalid_response=True)
    return items


def _homepage(item):
    if not isinstance(item, dict) or item.get("item_type") != 5 or item.get("success") != 1:
        return None
    path, name, clan = item.get("store_url_path"), item.get("name"), item.get("id")
    if (not isinstance(path, str) or not re.fullmatch(r"(?:developer|publisher|dev|pub)/[A-Za-z0-9_%.-]+/?", path)
            or not isinstance(name, str) or not name.strip() or len(name) > 200
            or isinstance(clan, bool) or not isinstance(clan, int) or not 0 < clan <= 4294967295):
        return None
    selector = {"kind": "homepage", "clan_id": str(clan)}
    # URL aliases do not establish whether the organization develops or publishes.
    return Creator(selector_id(selector), name.strip(), "Creator homepage", str(clan),
                   "https://store.steampowered.com/" + path, "", (), selector)


class CreatorSearchService:
    """Bounded search cache; a nonblocking lock caps concurrent discovery requests."""
    def __init__(self, clock):
        self.clock = clock
        self.cache = {}
        self.lock = threading.Lock()
        self.role_catalogs = CreatorCatalogService(clock)

    def search(self, client, term, region, role=None):
        if role is not None and role not in ("developer", "publisher"):
            raise ValueError("Choose developers or publishers.")
        key = (term.casefold(), region, role)
        cached = self.cache.get(key)
        if cached and self.clock() - cached[0] < 600:
            return cached[1]
        payload = client.get_json(_api_url("IStoreQueryService/SearchSuggestions", {
            "search_term": term, "max_results": 20, "search_creators": True,
            "context": {"language": "english", "country_code": region.upper()},
            "data_request": {"include_basic_info": True}}))
        response = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(response, dict) or not isinstance(response.get("metadata"), dict):
            raise HttpClientError("Steam returned an unreadable catalog search.", invalid_response=True)
        creators = {}
        for item in _store_items(payload):
            creator = _homepage(item)
            if creator:
                featured = next((c for c in FEATURED_CREATORS if c.clan_id == creator.clan_id), None)
                creators[creator.id] = (featured or creator).public()
        names = {creator["name"].casefold(): creator["name"] for creator in creators.values()}
        names.setdefault(term.casefold(), term)
        matches = []
        for name in names.values():
            try:
                name = validate_search_term(name)
            except ValueError:
                continue
            for kind in ((role,) if role else ("developer", "publisher")):
                creator = credit_creator({"kind": kind, "name": name})
                page = self.role_catalogs.get_page(client, creator, region, 0)
                if page["source"] == "stale cache":
                    raise HttpClientError("Steam could not verify matching catalogs.", transient=True)
                if page["total"] > 0:
                    matches.append(creator.public())
        data = {"creators": [] if role else list(creators.values()), "exact_matches": matches}
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (self.clock(), data)
        return data

    def resolve(self, client, selector, region):
        if selector["kind"] != "homepage":
            return credit_creator(selector)
        payload = client.get_json(_api_url("IStoreBrowseService/GetItems", {
            "ids": [{"creatorid": int(selector["clan_id"])}],
            "context": {"language": "english", "country_code": region.upper()},
            "data_request": {"include_basic_info": True}}))
        for item in _store_items(payload):
            creator = _homepage(item)
            if creator and creator.clan_id == selector["clan_id"]:
                return creator
        raise HttpClientError("Steam could not resolve this catalog.", invalid_response=True)
