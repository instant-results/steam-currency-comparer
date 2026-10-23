"""Anonymous, bounded Steam game discovery; prices use the existing batch worker."""
import json
import threading
from urllib.parse import urlencode

from .http_client import HttpClientError


class GameSearch:
    def __init__(self, clock):
        self.clock = clock
        self.cache = {}
        self.lock = threading.Lock()

    def search(self, client, query, country):
        if (not isinstance(query, str) or not 2 <= len(query.strip()) <= 100
                or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in query)):
            raise ValueError("Enter a game name between 2 and 100 characters.")
        query = query.strip()
        key = (query.casefold(), country)
        cached = self.cache.get(key)
        if cached and self.clock() - cached[0] < 600:
            return cached[1]
        payload = {"search_term": query, "max_results": 20, "search_creators": False,
                   "context": {"language": "english", "country_code": country.upper()},
                   "data_request": {"include_basic_info": True}}
        data = client.get_json("https://api.steampowered.com/IStoreQueryService/SearchSuggestions/v1/?" +
                               urlencode({"input_json": json.dumps(payload)}))
        response = data.get("response") if isinstance(data, dict) else None
        if not isinstance(response, dict) or not isinstance(response.get("metadata"), dict):
            raise HttpClientError("Invalid game search response", invalid_response=True)
        items = response.get("store_items", [])
        if not isinstance(items, list) or len(items) > 50:
            raise HttpClientError("Invalid game search response", invalid_response=True)
        found = {}
        for item in items:
            if not isinstance(item, dict) or item.get("item_type") != 0 or item.get("success") != 1:
                continue
            ident, name = item.get("id"), item.get("name")
            if type(ident) is not int or not 0 < ident <= 4294967295 or not isinstance(name, str) or not 0 < len(name.strip()) <= 300:
                continue
            found[str(ident)] = {"app_id": str(ident), "name": name.strip(),
                "kind": {0: "Game", 4: "DLC", 11: "Soundtrack"}.get(item.get("type"), "Steam app")}
        result = {"games": list(found.values())[:20]}
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (self.clock(), result)
        return result
