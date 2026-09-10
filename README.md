# Steam Prices Polisher

Compare Steam wishlist prices using a selectable baseline and up to two other
storefronts. The web app supports PLN (Poland), USD (United States), EUR (Germany),
NOK (Norway), and GBP (United Kingdom). The default remains PLN against USD/EUR.

## Run the web app

```powershell
python -m pip install -r requirements.txt
python .\serve_web.py
```

Open [Steam Prices Polisher](http://127.0.0.1:8765). Install the requirements once; HTTPS uses the operating system certificate store
with certificate and hostname verification enabled. Add a numeric SteamID64 or supported Steam profile URL, select
a baseline and one or two comparison storefronts, and watch prices arrive. Incoming results append in discovery order. Products with no regional price or
unavailable apps are hidden by default; use **Show unavailable products** to
reveal them. Technical failures remain visible. Column headers enable explicit
sorting, and **Discovery order** restores arrival order. Search, filter, or sort results;
cancel a run or retry it using completed cached prices. The example mode uses
clearly labeled illustrative prices without price requests; thumbnails load from Steam.

The web app supports **public wishlists only**. It ignores Steam cookies and the
local `wishlist.txt` file. A server-configured API key can resolve vanity URLs.
Jobs are private and temporary. Refresh reconnects within the same browser tab;
closing the tab or restarting the server loses job access. Completed regional
prices remain cached. Up to 1,000 games can be analyzed per wishlist.

For eventual public hosting, see [DEPLOYMENT.md](DEPLOYMENT.md). The WSGI service
includes bounded background jobs, input checks, same-origin POST protection,
private result tokens, and a persistent price cache. Deploy it as one Python
process behind HTTPS; this local version has not been published.

## Run the command-line prototype

Python 3.10 or newer is required. Numeric SteamID64 values and `/profiles/...`
URLs work without an API key:

```powershell
python .\steam_wishlist_compare.py 76561198000000000
```

## Choose comparison storefronts

The command-line prototype retains Poland (PLN) as its baseline. Select up to two
of the United States (`us`, USD), Germany (`de`, EUR), Norway (`no`, NOK), or the
United Kingdom (`gb`, GBP) with `--regions` after the Steam identifier:

```powershell
python .\steam_wishlist_compare.py 76561198000000000 --regions de
python .\steam_wishlist_compare.py 76561198000000000 --regions de us
```

Without `--regions`, the default is `us de`. Selection order is preserved in
results. Currency is determined by the storefront; arbitrary currency/region
pairs, duplicate regions, and the home region are rejected before requests or
cache initialization. The web sidebar additionally lets any of the five supported
storefronts become the baseline; it is not inferred from the Steam account. Run with `--help` for command-line help.

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

`FAIR` means the baseline price is no higher than **every** selected foreign price
converted to the baseline currency. This is a currency-conversion indicator, not a complete
judgment of consumer fairness or a checkout quote:

- No VAT or sales-tax adjustment is applied; displayed US and EU prices may
  have different tax treatment.
- Payment-provider fees and conversion costs are excluded.
- Germany is the EUR storefront proxy selected by this tool; prices elsewhere
  in the euro area may differ.
- Regional prices can be cached or fetched at different times.

The analysis result retains rate records and versioned methodology metadata for
use by the future interactive interface.

## Tests

```powershell
python -m unittest discover -v
```

Frontend rendering regression checks (Node.js):

```powershell
node --test tests/test_web_render.cjs
```

## Profile attribution and sale prices

The current profile and selected regions are restored with the comparison in the
same browser tab. Each new result also carries private profile attribution until
its one-hour expiry. Older sessions created before this feature cannot recover
an identifier that was never stored; start a new comparison once.

Each storefront retains its own final price, base price, and discount percentage.
The comparison uses final prices, including sales. The UI shows sale badges and
original-currency base prices; it never copies one region's discount to another.
Unknown metadata is labeled explicitly. Old price-cache entries are refreshed
on the next web comparison to obtain sale details. Web price freshness is one
hour for regular prices and 15 minutes for known sales; stale fallback is still
possible and clearly labeled. These are snapshots, not guaranteed checkout prices.

Steam policy sources: [Pricing](https://partner.steamgames.com/doc/store/pricing?l=english)
and [Discounting](https://partner.steamgames.com/doc/marketing/discounts?l=english).
Publishers set regional base prices; minimum transaction thresholds can affect
local availability. Discounts reference established base or introductory launch
prices. The public documentation does not provide a blanket guarantee that every
regional offer has the same discount, so this tool checks each independently.

## Regional discount assumptions and retrieval cost

Research checked on 2026-09-10, including community observations outside Valve's
policy documentation:

- During Sekiro's April 2022 promotion, users reported a 50% discount in Western
  regions but no discount in parts of Asia. See the
  [contemporaneous Steam Community report](https://steamcommunity.com/discussions/forum/1/3279192886604240573/)
  and [independent Reddit discussion](https://www.reddit.com/r/Steam/comments/uc1qof/).
- These are historical user reports about regional offers. They are not a fresh
  live measurement or proof that the same package can receive different
  per-currency percentages. Regional publishers/packages are a possible explanation.
- Accordingly, the app does not assume that every regional offer for one app
  shares its sale status. It retains the actual returned values for each region.

This does not add a separate discount request. Each existing regional
`appdetails` response includes the currency, final price, base price (`initial`),
and `discount_percent`. A cold comparison with PL/US/DE still needs up to three
price requests per game, whether discounts are inspected or ignored. Missing
home prices can stop the comparison early; fresh cache entries avoid requests.

Applying a home-region discount to cached foreign base prices could reduce some
future refresh requests, but those prices would be estimates: base prices and
availability can change, regional offers can differ, and rounding matters. This
optimization is not enabled. Preserve observed final prices for the current
comparison; consider measured concurrency or caching improvements separately.


## Discount differences and percentage comparison

Products with unequal known regional discount percentages carry a **Different
regional discounts** badge and can be isolated with the **Different discounts**
filter. This includes sale versus no sale. Unknown metadata is not treated as
zero discount. Hover over the badge for the observed regional percentages;
cached observations at different times can also explain a mismatch.

Each comparable product shows the absolute baseline-currency difference and percentage:
`(baseline final price - cheapest selected alternative in baseline currency) / cheapest selected alternative in baseline currency * 100`.
Negative means cheaper in the baseline storefront. Percentages are rounded to one decimal place;
a zero reference price shows “Percentage unavailable”. Both additions reuse
existing results without extra Steam requests.


## CSV export

Download CSV exports all currently loaded results, including products hidden by
filters. A running comparison exports only its completed results so far. There
is one row per game/storefront and one row for each uncompared game. Wishlist
profile attribution is optional and off by default; access tokens are never exported.

The UTF-8 CSV includes original/base/final prices, discounts, prices converted to the baseline currency,
absolute and percentage differences, and exchange-rate provenance. NBP publication
date, original successful retrieval time, and the comparison's rate-check time
are separate fields. Timestamps use UTC. A cache check does not imply a new NBP
request. Older in-memory results without timestamps export blank fields; run a
new comparison after restarting the server to obtain them. PLN identity conversion
has no NBP timestamps. Example exports are marked as illustrative data.

CSV is intended for spreadsheets and analysis; numeric values use decimal points.
Untrusted text starting with spreadsheet formula characters is prefixed with an
apostrophe. JSON could preserve nested results more naturally, but is not currently
offered. Export is generated locally in the browser without additional requests.


## Storefront thumbnails

Each title links to Steam with a lazy-loaded header thumbnail from Steam's image
CDN. Fixed image slots and reused rows avoid layout shifts; unavailable artwork
shows a neutral fallback. Images use app IDs already in the results, so there are
no additional regional price requests. Browsers fetch artwork directly from
`shared.akamai.steamstatic.com` without a referrer. The image policy allows only
that external host. Restart the local server after this change to apply the policy.


## Readability and sorting

Foreign final prices now use 16px text. Column headings identify Game name and
the baseline storefront. Difference offers independent absolute and percentage sort buttons;
repeated clicks reverse direction, with unavailable percentages last. Uncompared
shows contextual help explaining missing prices, failed requests, and the separate
availability toggle. Storefront labels remain geographic: currency alone does not
establish identical regional offers.


## Five-currency baseline selection

The flag/header badge is removed. Select a baseline in the left sidebar and up
to two other currencies below it. The baseline cannot also be an alternative;
once two alternatives are checked, uncheck one before choosing another. One
alternative is allowed. Both browser controls and the server enforce the limit.
Supported pairs are PL/PLN, US/USD, DE/EUR, NO/NOK, and GB/GBP, matching
[Steam's supported currencies](https://partner.steamgames.com/doc/store/pricing/currencies).

NBP reports PLN per currency unit. The conversion into baseline currency B is
`rate_to_pln[A] / rate_to_pln[B]`; PLN has an identity rate of 1. The rate notebook
retains the underlying PLN quotes and dates. CSV additionally includes the
baseline storefront/currency, derived conversion factor, and baseline rate's
publication/retrieval/check times and cache status, preserving both conversion
legs. Final-price and difference columns now use baseline-neutral names.

Selections persist with the saved comparison and retry request. Changing form
choices does not relabel existing results: their baseline remains the one used
for that run. Old saved requests without a baseline default to Poland. Examples
use the selected baseline and alternatives. Restart the server for the new API.
