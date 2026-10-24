"""Resolve supported Steam organization addresses without fetching arbitrary URLs."""
from __future__ import annotations

import json
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .http_client import HttpClientError, UrllibJsonHttpClient

URL_HELP = "Enter a Steam developer/publisher homepage or a Steam search URL with one developer or publisher."
STEAM_HOSTS = {"store.steampowered.com", "www.steampowered.com", "steampowered.com"}


def is_organization_url(value):
    return isinstance(value, str) and bool(re.match(
        r"(?i)^(?:[a-z][a-z0-9+.-]*://|(?:https?|file|javascript|data):|//|(?:store\.|www\.)?steampowered\.com(?:/|$))", value.strip()))


def parse_organization_url(value):
    """Discard tracking/locale parameters and reconstruct a fixed Steam address."""
    if not isinstance(value, str) or len(value) > 1024 or any(ord(c) < 32 for c in value):
        raise ValueError(URL_HELP)
    text = value.strip()
    if "://" not in text:
        text = "https://" + text
    try:
        url = urlsplit(text)
        if (url.scheme not in {"http", "https"} or url.hostname not in STEAM_HOSTS
                or url.port is not None or url.username is not None or url.password is not None
                or "\\" in text):
            raise ValueError(URL_HELP)
        if url.path in {"/search", "/search/"}:
            query = parse_qs(url.query, keep_blank_values=True, max_num_fields=50)
            roles = [role for role in ("developer", "publisher") if role in query]
            if len(roles) != 1 or len(query[roles[0]]) != 1:
                raise ValueError(URL_HELP)
            name = query[roles[0]][0].strip()
            if not 2 <= len(name) <= 100 or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in name):
                raise ValueError(URL_HELP)
            return {"kind": "credit", "role": roles[0], "name": name}
        match = re.fullmatch(
            r"/(developer|publisher|dev|pub)/([^/]+)(?:/(?:about|games|lists|list/[0-9]+))?/?", url.path)
        if match:
            alias = unquote(match[2], errors="strict")
            if not re.fullmatch(r"[\w .-]{1,100}", alias, flags=re.UNICODE) or alias in {".", ".."}:
                raise ValueError(URL_HELP)
            return {"kind": "homepage", "url": "https://store.steampowered.com/"
                    + match[1] + "/" + quote(alias, safe=".-_") + "/"}
        match = re.fullmatch(r"/curator/([1-9][0-9]{0,9})(?:-[\w%-]+)?(?:/(?:about|games|lists|list/[0-9]+))?/?", url.path)
        if match and int(match[1]) <= 4294967295:
            return {"kind": "homepage", "url": "https://store.steampowered.com/curator/" + match[1] + "/",
                    "clan_id": match[1]}
    except (ValueError, UnicodeError):
        pass
    raise ValueError(URL_HELP)


class HomepageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.app_ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and len(self.app_ids) < 12:
            match = re.match(r"https://store\.steampowered\.com/app/([1-9][0-9]{0,9})(?:/|$)", attrs.get("href", ""))
            if match and int(match[1]) <= 4294967295 and match[1] not in self.app_ids:
                self.app_ids.append(match[1])


def parse_homepage(payload):
    # Read only the observed literal; never execute upstream scripts or forward HTML.
    match = re.search(r"\bvar\s+g_pagingData\s*=\s*(\{[^;]{1,4096}\})\s*;", payload)
    if not re.search(r"\bvar\s+g_bIsCreatorHome\s*=\s*true\s*;", payload):
        raise HttpClientError("This Steam page is not a developer or publisher homepage.", invalid_response=True)
    try:
        if match:
            clan = json.loads(match[1])["clanid"]
        else:
            # Newer homepages render their products in JavaScript and omit pagingData.
            ids = set(re.findall(r"\bFollowCurator\(\s*([1-9][0-9]{0,9})\s*,\s*(?:true|false)\s*\)", payload))
            if len(ids) != 1:
                raise ValueError()
            clan = int(ids.pop())
        if type(clan) is not int or not 0 < clan <= 4294967295:
            raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise HttpClientError("Steam returned an unreadable organization homepage.", invalid_response=True) from exc
    parser = HomepageParser()
    parser.feed(payload)
    return {"clan_id": str(clan), "app_ids": parser.app_ids}


class HomepageRedirect(HttpClientError):
    def __init__(self, url):
        super().__init__("Steam redirected the organization homepage.")
        self.url = url


class HomepageRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            parsed = parse_organization_url(newurl)
            if parsed["kind"] != "homepage":
                raise ValueError()
        except ValueError as exc:
            raise HttpClientError("Steam redirected to an unsupported organization page.", invalid_response=True) from exc
        # The service follows this through the shared pacing/retry client.
        raise HomepageRedirect(parsed["url"])


class OrganizationHttpClient(UrllibJsonHttpClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._opener.add_handler(HomepageRedirectHandler())

    def get_json(self, url, headers=None):
        if urlsplit(url).hostname == "store.steampowered.com" and re.fullmatch(
                r"/(?:developer|publisher|dev|pub|curator)/[^/]+/?", urlsplit(url).path):
            return parse_homepage(self._read_payload(url, headers, maximum_bytes=2_000_000))
        return super().get_json(url, headers)
