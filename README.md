# Steam Prices Polisher

Compare the PLN prices of games on a Steam wishlist with prices from selected
Steam regions after currency conversion.

## Run the command-line prototype

Python 3.10 or newer is required. Numeric SteamID64 values and `/profiles/...`
URLs work without an API key:

```powershell
python .\steam_wishlist_compare.py 76561198000000000
```

## Custom Steam profile URLs

Steam requires a user Web API key to translate a custom `/id/name` URL into a
numeric SteamID64. Register a user key at
<https://steamcommunity.com/dev/apikey>, then expose it only to the current
process:

```powershell
$env:STEAM_WEB_API_KEY = "your-key"
python .\steam_wishlist_compare.py https://steamcommunity.com/id/example
```

The key is not written to the cache or repository. When it is absent, the tool
explains that vanity resolution was skipped and still tries the legacy wishlist
endpoint. You can always use a numeric SteamID64 instead.

Do not commit a populated `.env` file. The project does not automatically load
`.env`; `.env.example` only documents the supported variables.

## Tests

```powershell
python -m unittest discover -v
```
