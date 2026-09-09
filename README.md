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

## Choose comparison storefronts

Poland (PLN) remains the home storefront. Select the United States (`us`, USD),
Germany (`de`, EUR), or both with `--regions` after the Steam identifier:

```powershell
python .\steam_wishlist_compare.py 76561198000000000 --regions de
python .\steam_wishlist_compare.py 76561198000000000 --regions de us
```

Without `--regions`, the default is `us de`. Selection order is preserved in
results. Currency is determined by the storefront; arbitrary currency/region
pairs, duplicate regions, and the home region are rejected before requests or
cache initialization. The catalog currently supports only these three
storefronts, with Poland as home. Run with `--help` for command-line help.

## Rates and comparison methodology

The results include each currency's NBP table A mid rate, its publication
(`effectiveDate`) date, and whether it came from a live request, cache, or stale
cache. See the [NBP API documentation](https://api.nbp.pl/en.html). The publication
date is separate from the time the application fetched the rate; currencies can
have different publication dates.

Rates are cached for 24 hours. If refresh fails and all needed rates have cached
values, the tool can use them with a visible stale-cache warning. Existing cache
entries migrate automatically; rates without dates are refreshed, or explicitly
shown with an unknown date when refresh fails. Fallback does not reset cache age.

`FAIR` means the Polish price is no higher than **every** selected foreign price
converted to PLN. This is a currency-conversion indicator, not a complete
judgment of consumer fairness or a checkout quote:

- No VAT or sales-tax adjustment is applied; displayed US and EU prices may
  have different tax treatment.
- Payment-provider fees and conversion costs are excluded.
- Germany is the EUR storefront proxy selected by this tool; prices elsewhere
  in the euro area may differ.
- Regional prices can be cached or fetched at different times.

The analysis result retains rate records and versioned methodology metadata.

## Tests

```powershell
python -m unittest discover -v
```
