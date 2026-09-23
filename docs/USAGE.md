# Usage and technical reference

For installation and your first comparison, start with the [README](../README.md).

## Local operation and loading order

Keep the launching terminal open. Stop the preview with Ctrl+C (or Ctrl+Break on
Windows); it also exits if the launching process terminates. A second instance
on the same port is rejected. Before restarting, verify that port 8765 has no
listeners; after starting, verify exactly one listener and a successful response
from `/api/health`. Old versions may need their confirmed app process stopped
explicitly. Use `python serve_web.py --port 8766` to select a different port.

Live Steam and NBP requests require outbound network access from the server.
When using an agent's network-restricted sandbox, launch the preview with approved
outbound access. A "network access is blocked by local permissions" error means
the server's sandbox, firewall, or OS permissions need attention; restarting with
appropriate access is required before retrying. This is separate from an upstream
HTTP rejection or outage. Blocked requests are not automatically retried.

The web app supports **public wishlists only**. It ignores Steam cookies and the
local `wishlist.txt` file. A server-configured API key can resolve vanity URLs.
Jobs are private and temporary. Refresh reconnects within the same browser tab;
closing the tab or restarting the server loses job access. Completed regional
prices remain cached. Up to 1,000 games can be analyzed per wishlist.

Your Rank loads the lowest Steam wishlist priority number first. Date Added loads
the newest additions first. Items without the selected metadata retain their
relative order at the end. Steam's current wishlist response usually omits game
names, so alphabetical loading first resolves the baseline storefront details
needed to learn every name; those baseline results are reused during comparison
instead of being requested twice. The chosen order is retained for refresh and
retry within the browser tab.

For eventual public hosting, see [DEPLOYMENT.md](../DEPLOYMENT.md). The WSGI service
includes bounded background jobs, input checks, same-origin POST protection,
private result tokens, and a persistent price cache. Deploy it as one Python
process behind HTTPS; this local version has not been published.

## Run the command-line prototype

The sample SteamID64 `76561198000000000`, `/id/example` URL, and `your-key`
are placeholders; replace them with your own values. They are not a working demo.

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

Analysis results retain rate records and versioned methodology metadata for UI
rendering and exports.

## Diagnostic events

The web app and preview write structured JSON Lines events to
`.steam-price-polisher/logs/events-<PID>.jsonl` by default. If
`STEAM_PRICE_POLISHER_DATA_DIR` is set, logs live in its `logs` subdirectory.
Each process has its own file so duplicate startup attempts cannot interfere
with another server's rotation. Files rotate at 2 MiB, keeping three backups
per process (about 8 MiB total). Files from previous processes remain available;
remove those old files when no longer needed. Generated event files are ignored
by Git. Logging uses Python's standard library; no external service is involved.

Normal logs include server startup, shutdown reason, startup failures, job
queue/start/cancellation/completion/failure, and upstream request failures with
service, operation, attempt, timing, status/socket code, and retry decision.
Successful requests, cache provenance, and idle/closed client connections are
included only at DEBUG level:

```powershell
$env:STEAM_PRICE_POLISHER_LOG_LEVEL = "DEBUG"
python serve_web.py
```

Restart with `STEAM_PRICE_POLISHER_LOG_LEVEL=INFO` (the default) for normal detail.
The terminal stays at INFO even in debug mode. Set variables in the launching
shell; the project does not automatically load `.env`. The CLI does not configure
file logging automatically.

Events contain a UTC timestamp and process ID. Use `job_id` to connect a job's
lifecycle to its requests and cache events; it is the internal job ID returned
when a comparison starts, not its access token. The logger records counts, not
game lists or prices. It excludes profiles, IP addresses, API keys, cookies,
tokens, URLs, headers, response bodies, and raw exception text. Unexpected errors
retain their exception type and an allowlisted project code location, without
locals, source lines, or absolute paths. Log files are local diagnostics and
are not served by the web app. File logging failures leave the server running
with console diagnostics and a fixed warning.

## Tests

```powershell
python -m unittest discover -v
```

Frontend rendering regression checks (Node.js):

```powershell
node --test tests/test_web_render.cjs
```

Repeatable preview lifecycle checks (included in the Python suite):

```powershell
python -m unittest tests.test_server_lifecycle -v
```

These launch temporary servers on available loopback ports, verify health,
duplicate-instance rejection, shutdown and restart, and loss of the launching
process. They use temporary data directories and make no external requests.

## Profile attribution and sale prices

The current profile, selected regions, baseline, and loading order are restored
with the comparison in the same browser tab. Each result also carries private
profile attribution until its one-hour expiry.

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
shows a neutral fallback. Hovering over either the artwork or title shows the
Steam App ID. Images use app IDs already in the results, so there are
no additional regional price requests. Browsers fetch artwork directly from
`shared.akamai.steamstatic.com` without a referrer. The image policy allows only
that external host.


## Readability and sorting

Foreign final prices use 16px text. Column headings identify Game name and
the baseline storefront. Difference offers independent absolute and percentage sort buttons;
repeated clicks reverse direction, with unavailable percentages last. Uncompared
shows contextual help explaining missing prices, failed requests, and the separate
availability toggle. Storefront labels remain geographic: currency alone does not
establish identical regional offers.


## Baseline and comparison selection

Select a baseline in the left sidebar and up to two other currencies below it.
The baseline cannot also be an alternative;
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
use the selected baseline and alternatives.


## Remembered comparison selections

Changing the baseline temporarily excludes conflicting comparison currencies
without forgetting them. Returning to a non-conflicting baseline restores them.
Explicit checkbox edits replace the remembered choices, so a newly selected pair
wins over a previously hidden currency and the two-alternative limit remains intact.
Restoring a saved comparison replaces the preferences with that run's selections.
Regression tests exercise actual change handlers, repeated switches, explicit
replacement/deselection, welcome captions, busy state, and saved restoration.

## Continuing development

Read [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) for the concise current-state
handoff and [AGENTS.md](../AGENTS.md) for collaboration and Git preferences.
Follow the preview lifecycle guidance above. Inspect the repository state before continuing; Git history is
the detailed change history. Read
[docs/STEAM_SORTED_WISHLIST_API.md](STEAM_SORTED_WISHLIST_API.md) before
changing wishlist retrieval or adding Steam-compatible loading orders.
