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
names, so alphabetical loading first resolves StoreBrowse metadata for sorting.
Those observations are reused. Other orders prepare up to 100 games at a time,
then append the window's rows in order. The chosen order is retained for refresh
and retry within the browser tab.

For eventual public hosting, see [DEPLOYMENT.md](../DEPLOYMENT.md). The WSGI service
includes bounded background jobs, input checks, same-origin POST protection,
private result tokens, and a persistent price cache. Deploy it as one Python
process behind HTTPS. The source is published on GitHub; the app has not been
deployed as a public service.

## Automatic example on a fresh visit

On a fresh visit, the wishlist tab automatically compares seven selected games
using the current baseline and comparison currencies. The example is labeled and
uses live Steam prices and NBP rates through the normal shared cache. No profile
is needed, and there is no separate example button.

An existing saved wishlist comparison reconnects first, including its retry
context if the server job has expired. An example never replaces that comparison.
Saved catalog jobs also reconnect before automatic work, even on hidden tabs.
If another comparison is running, the example waits until work finishes and the
wishlist tab is visible. Typing a profile dismisses a pending example; submit
**Compare regional prices** to compare your own wishlist. A failed or cancelled
example is retried only with **Retry comparison**.

All comparison tabs use one frontend coordinator for job starts, shared control
locking and automatic work that waits for idle. User-started work reserves the
worker immediately; catalog auto-loading has priority over a queued example.
The server's shared worker, request pacing and job limits still apply.

## Change currencies after loading

Currency selection sits above the full-width comparison. The selectors collapse
when a run starts or saved results are restored; **Change currencies** reopens
them without changing results. The button sits beside the selection summary;
**Update currencies** appears only in the expanded panel. **Hide currencies**
discards unapplied changes and restores the active tab's displayed currencies.
Before any results exist, hiding restores the choices from opening setup instead.
Automatic collapse when submitting preserves the requested currencies. Picker
lists sit side by side on wider screens and stack on phones. During loading,
reopening is allowed but selection stays locked.

After a wishlist/example or catalog comparison finishes, select a baseline and
one or more other storefronts, then click **Update currencies** in the currency panel.
The button is available when the valid selection differs from the displayed
comparison. It updates the current tab. Other tabs keep their own comparisons;
the displayed-currency captions identify the selection used by their results.
Currency changes during loading are disabled across all tabs.

The previous comparison remains visible while a separate job prepares the update.
Its rows, headings, exchange rates, statistics and CSV remain together until the
update reaches complete or partial completion, when the new snapshot replaces them.
Search, filters, sorting, scroll position, expanded catalogs, credit-column mode
and the best-offer checkbox are preserved. Search/filter/sort and CSV remain usable
while an update runs; exported data always describes the displayed comparison.

Wishlist/example updates normally use the retained game list and loading order
without fetching the wishlist again while the source job remains available.
Catalog updates deduplicate all loaded product IDs for retrieval, then keep their
original groups and display order. Both default prices and best offers reuse the
existing cache and independent freshness rules;
only missing or expired selected-country observations need retrieval. Even fully
cached updates are asynchronous and show progress.

Cancel returns to the previous snapshot. A failed submission, failed job or expired
pending job also leaves it available. **Retry currency update** repeats the failed
selection using the original source. A partial update becomes the new comparison,
with missing prices and technical failures represented as uncompared products.
Reload in the same browser tab restores the displayed snapshot, wishlist view
settings and pending job credentials separately, reconnecting active updates even
on hidden catalog tabs. If the source wishlist job has expired or the server has
restarted, Update currencies automatically starts a replacement comparison using
the saved source, loading order and requested currencies. The example is recreated;
a personal wishlist is fetched again and may reflect list changes since the saved
comparison. Previous results stay visible until replacement completes. Failed or
cancelled replacements retain that snapshot and can be retried, including after
refresh. Catalog updates can still use their locally saved IDs.

Catalog page cursors retain their discovery storefront. After changing the baseline,
**Load more** starts at the first page for the new storefront and deduplicates
against loaded products. It resumes an existing cursor only when its storefront
matches. The current tab's **Refresh comparisons** also preserves displayed results
until its loaded-product update finishes; after a failed update it retries that
selection. Adding or expanding catalogs continues using their displayed currencies.

## Remove titles from a comparison

Hover over a game's thumbnail to reveal the circular × overlapping its top-right
corner. Keyboard focus within the thumbnail reveals it too; on touch devices, hold the thumbnail for half a second, release, then tap ×.
Scrolling or tapping elsewhere hides it. Ordinary taps still open Steam. A hint
appears until the first successful hold in the browser tab. The button removes the entire title, including its default and best
offers, from the current comparison. Rows, counts, catalog statistics and CSV
update immediately. This differs from search and display filters: removed titles
are excluded from exports even while Undo remains available.

Each removal creates a pale-blue notice fixed near the bottom center of the
viewport. It identifies the title and Steam App ID and offers **Undo** for seven
seconds. Hovering or focusing a notice does not pause its timer. The stack holds
at most four notices: three standard-height notices and an oldest notice at 65%
height. A fifth removal immediately finalizes the oldest one. Each remaining
notice keeps its own deadline. Undo restores original loading order and all
applicable catalog memberships; current filters and sorting still apply.

In Developers or Publishers, removing a title removes it from every selected
catalog in that tab. Their counts, average/median differences and coverage update
together. Other tabs retain their independent comparisons. Steam wishlist and
account contents are not changed.

The browser keeps removed row data only in the temporary Undo buffer, not in
session storage or CSV. Expiry or early finalization releases that buffer and
requests permanent cleanup of retained server-job records and loaded selections.
Small ID-only exclusion lists prevent late results from reintroducing rows.
Shared regional price and metadata caches retain their normal freshness rules.
If server cleanup cannot connect, it retries using IDs and job credentials without
keeping the deleted row data. Reload resumes pending cleanup from saved exclusions.

Removal survives polling, currency updates, catalog expansion and reload
in the same browser tab. Currency updates during Undo retain the pending title in
their retrieval selection so Undo can restore prices in the newly displayed
currencies. Reloading/leaving the page or explicitly starting a new wishlist
comparison ends the previous Undo window. A new wishlist comparison starts with
the full fetched list; previously removed titles may appear again.

For programmatic cleanup, same-origin JSON POST `/api/jobs/{id}/remove` accepts
`{"app_ids":["413150"]}` with that job's bearer token. This is a permanent,
idempotent operation; it removes retained row records, source selections and
catalog memberships, including before a running worker emits the title. It does
not delete shared price caches. Recreated wishlist or catalog submissions can
include an `excluded_app_ids` list; input validation permits up to 10,000 distinct
numeric IDs. The browser applies the Undo window before invoking cleanup.

Removal history retains up to 10,000 App IDs per comparison tab. Additional
removal at the limit is refused with an explanation. Cleanup uses batches of
1,000 IDs; fetched-product limits remain unchanged. **Retry comparison** starts
a fresh wishlist comparison, clears removals and ends pending Undo notices.
**Update currencies** and **Retry currency update** retain removals.

## Add individual games

Use the same field as the Steam profile. A 17-digit SteamID64 or profile URL
loads a wishlist; a game App ID or Steam `/app/` URL adds a game to the current
comparison. Enter a name and pause typing for four seconds (or press Search games),
then choose Add to the left of the intended match. DLC and soundtracks are labeled
separately. Package and bundle URLs are not accepted as App IDs. Search uses the displayed baseline
storefront and needs no key, cookies or sign-in; availability and matches can vary
by country. It is a bounded suggestion list, not an exhaustive catalog search.

An idle comparison starts the addition immediately. Games selected while work is
running appear in a queue below the field; selections already waiting are combined
when the worker becomes available. There is no deliberate batching timer. Duplicate
selections are ignored. Remove queued games before they start, or cancel an active
addition and explicitly retry the saved queue later. Name search alone does not
start a price comparison. Up to 1,000 games, including queued additions, are allowed.

Additions use the displayed currencies, even when the setup panel contains unapplied
choices. Existing results remain visible until the new complete/partial snapshot is
ready. The worker compares the retained selection and new IDs together, reusing fresh
observations and refreshing expired ones, so prices and exchange rates remain consistent.
The original wishlist is not fetched again for an addition. Failed additions leave
the prior snapshot intact. Reload reconnects active additions or offers retry after
expiry. Restored queued work waits for any active comparison. Starting another
wishlist replaces the comparison and clears its pending additions.

Manual games carry a Manually added label; even missing-price manual rows stay visible
unless hidden by an explicit filter. They participate in counts, sorting, currency
updates, removal and CSV. Explicitly adding a removed game clears its exclusion for
the new job; old-job cleanup cannot remove it from that new job. Undo remains available
for seven seconds. No action modifies the actual Steam wishlist.

CSV schema 1 appends `manually_added` (true/false). Manual rows have no wishlist-profile
attribution, even when profile export is enabled, and are not labeled example data.
Saved comparisons with explicit selections recreate those IDs after server expiry,
including manual additions; they do not need to rediscover the wishlist. Retry comparison
rechecks the retained selection. Submitting a profile again loads its current wishlist.

### Backend game search and explicit selections

Send a same-origin JSON POST to `/api/games/search` with
`{"query":"Hades","home":"pl"}`. Names must contain 2 to 100 characters after
trimming. The response contains `games`, with `app_id`, `name` and `kind` for each
match. Steam SearchSuggestions supplies up to 20 app matches; packages and bundles
are excluded. Successful searches are cached for ten minutes by case-insensitive
query and storefront, with at most 128 cache entries. One game search runs at a
time, sharing Steam request pacing with comparisons. Busy searches return 429;
upstream failures return a controlled 503 error. No job token is required.

To compare an exact selection, POST to `/api/jobs` with the usual `identifier`,
`home`, `regions` and optional `order`, plus `app_ids` and `added_app_ids`.
Each supplied ID list contains 1 to 1,000 unique canonical positive 32-bit App ID
strings; `added_app_ids` must be a subset of `app_ids` when both are supplied.
Use `identifier: "selection"` with a nonempty `app_ids` list when no profile is
associated with the comparison. Explicit `app_ids` preserve list order and skip
wishlist discovery. `added_app_ids` marks manual provenance; without `app_ids`,
these IDs are appended to the discovered wishlist, subject to the total game limit.
The existing job-token polling, cancellation, removal and currency-update routes
apply. Currency updates retain the exact selection and manual provenance.

## Owned library

**Deferred / hidden by default.** This prototype is retained for internal testing;
it is not an available feature in the normal app. Successful authenticated live
API retrieval is TODO until Steam Guard/key setup can be completed. Merely setting
STEAM_WEB_API_KEY does not enable it. See the [validation criteria](ROADMAP.md#deferred-stage-the-users-owned-library).

The server's internal OWNED_LIBRARY_ENABLED flag defaults to false. Isolated QA
can explicitly construct WebApplication with owned_library_enabled=True; this
opt-in enables both the tab and its job endpoint. Normal runs hide the tab/form,
skip initialization and saved-job reconnection, and reject /api/library-jobs.
Saved library session state is preserved for later QA and cannot lock the visible
controls or change currencies. Keyboard navigation covers the three visible tabs;
a saved library selection falls back to Your wishlist.

The following describes the prototype when explicitly enabled for internal QA.
Its **Owned library** tab appears immediately to the right of **Your wishlist**. Enter a
17-digit SteamID64 or a Steam community `/profiles/` or `/id/` profile URL.
It uses the same table, credits, filters, sorting, unavailable toggle, sale-price
handling, cancel/retry actions, and shared currencies as the wishlist. It shows
current storefront prices for games you own, not historical purchase prices.

Steam's owned-games API requires a Web API key for numeric profiles too. Register
your own [Steam user Web API key](https://steamcommunity.com/dev/apikey), then set
it in the terminal that launches an explicitly enabled internal QA server:

```powershell
$env:STEAM_WEB_API_KEY = "your-key"
```

On macOS/Linux, use `export STEAM_WEB_API_KEY="your-key"` before starting the
server. Replace the placeholder locally and keep the key out of chat, Git, and
browser profile fields. Restart the server after configuring the key.
The project does not automatically read `.env`. Wishlist and catalog comparisons
still work without a key when custom profile resolution is not needed.

Set profile **Game details** to **Public**. The app uses no Steam sign-in/cookies
and changes no privacy settings. Missing or rejected keys have specific messages.
A response without an exposed library reports private or unavailable Game details
rather than claiming it is empty. Explicitly empty libraries complete without
exchange-rate or price requests.

**Name** is the default loading order; **Steam order** preserves the API's order,
without implying purchase dates, playtime, or wishlist priority. Free-to-play
games are excluded in the request. The returned games are not a full license/DLC
inventory; individual private games may be hidden. Products without current prices
follow wishlist unavailable/uncompared rules. Up to 1,000 distinct games can be
compared; larger libraries fail explicitly without silently truncating results.
See the [retrieval research](STEAM_OWNED_LIBRARY_API.md) for credentials and coverage.

Library results, filters, sorting, profile, currency settings, and job access are
saved independently under `polisher-library-job` in session storage. Completed
results survive reload in the same tab, even after server jobs expire. Active jobs
reconnect; retry uses that run's settings. Changing currency-panel choices does not
relabel results; submit the profile again to compare with new choices. All four
tabs share one paced worker and job locking. Return to the owning tab to cancel.
Price/rate caches are shared; ownership mappings are never saved in the server cache.

CSV uses the shared schema with `source_tab=library`. `library_profile` is blank
unless **Include library profile** is checked (off by default), and
`library_loading_order` records `name`/`steam`. Wishlist/catalog attribution stays
blank. Export includes checked results hidden by filters and adds no requests.
Credentials never appear in CSV.

## Developer and publisher catalogs

Developer and publisher name searches run after four seconds without edits,
matching wishlist game search. Search Steam submits immediately. Editing or
clearing the query discards outdated matches; switching tabs cancels pending
automatic search. Search does not start a price comparison.

Open **Developers** or **Publishers** beside **Your wishlist**. Developers starts
with three selected games each from Supergiant Games, CD PROJEKT RED, and Techland.
Publishers features Devolver Digital (US), THQ Nordic (Austria), and 11 bit studios
(Poland), with examples developed by other studios. See [featured catalogs](FEATURED_CATALOGS.md)
for the selected games and verification sources. Each tab compares its starting games
using the currency panel's baseline and comparison currencies.
Names and artwork appear immediately; prices and differences fill in as requests
complete. **Load more** expands products whose Steam store pages credit that
exact name as developer or publisher, depending on the tab. Catalogs include
paid DLC, soundtracks, and other products. Free products, including demos, are
removed after checking; missing regional prices alone do not imply free.

Steam can return its default 25-entry search page despite the requested 12 entries.
Pagination advances through every returned slot, including skipped packages and
bundles. Already displayed examples are not duplicated, and Load more disappears
at the end. Free-only pages still advance; use Load more again to continue.

Use **Find a developer** or **Find a publisher** in the corresponding tab.
Only names with matching products for that role in the baseline region are
returned. **Add** appends that catalog beside the featured entries.
There is no Creator role or homepage-catalog button. Steam homepage suggestions
are used internally to discover possible names, then their product credits are checked.
Use the full credited name: spelling, regional availability, and Steam filters
can affect coverage. Searches take names, not pasted URLs, and need no Steam login
or API key. Discovery uses a ten-minute bounded cache with six-hour role-page caching;
searching alone does not fetch regional prices.

The two catalog tabs keep independent results, selections, catalog positions,
and searches when switching tabs. Completed comparisons and selected catalogs
survive reload in the same browser tab. Up to 20 catalogs can appear per role.
When defaults change, former featured entries are replaced while user-added
catalogs and their pagination remain. New defaults are compared automatically.
Older combined-tab selections migrate only when they carry an explicit developer
or publisher selector; old homepage catalogs are not assigned a role.
New entries use the Steam-logo fallback. Existing results retain their comparison
currencies until **Update currencies** or **Refresh comparisons** applies the currency-panel choices.

Search remains available during comparisons, while adding, refreshing, and
expanding catalogs wait for the active comparison to finish or be cancelled.
Return to the tab running the comparison to cancel it. The visible tabs and internally enabled library share the
paced worker and price cache. See the [search implementation notes](STEAM_CREATOR_SEARCH.md).

The footer labels the initial curated selection as **featured games**. That label
disappears once the catalog expands, including after changing the baseline or
restoring saved results. Expanded footers show the loaded product count and,
when available, Steam's catalog total. The total may include free products that
are excluded from the displayed list.

Each developer's or publisher's icon and name sit above its games, beside an average percentage
difference for each selected foreign storefront. Each compared, loaded product
has equal weight: `(baseline price - converted foreign price) / converted foreign
price * 100`. The mean uses unrounded differences; negative means cheaper in the
baseline, positive means pricier. Missing, pending, free, and zero-reference
products do not contribute. Each average shows its own sample count. Below each
average, the median shows the middle product difference after sorting; with an
even sample size it averages the two middle differences. Both use the same sample
and unrounded calculations.
The header also reports comparison coverage and cheaper/equal, pricier, uncompared,
and pending counts. Cheaper/equal means the baseline price is no higher than every
selected converted foreign price. These statistics describe loaded products only,
including paid DLC and soundtracks; they do not summarize the entire Steam catalog.
Statistics use existing comparison results without additional requests, update
when more products load, and retain the results' currencies until refreshed.

One shared column-heading row sits above all creators. Its sort buttons cycle
ascending, descending and original order for game name, baseline price, absolute
difference and percentage difference. Each catalog sorts its own titles; catalogs
keep their positions. Missing numeric values stay last. Each role remembers its
sort through reload, expansion and currency updates. Wishlist rank/date loading
orders do not apply to catalogs. Regional headings and
prices align in fixed-width slots and scroll together; game/title, baseline and
DIFFERENCE stay pinned. Per-currency statistics are a separate overview, expandable
when more than four alternatives are selected; expansion survives display changes
and reload. Dividers mark the pinned baseline and DIFFERENCE boundaries.
Narrow screens place identity above the price row, keeping the baseline and
DIFFERENCE at its edges. Catalog tables use synchronized horizontal scrolling.
The arrow is shallow, has a flat top and no visible border, and fades most strongly
at its top center; its white label remains accessible to keyboard and screen-reader
users. The introduction keeps the free-product note, progress status, and statistics
explanation with consistent text sizing. The exclusion note sits on its own line.
Currency choices appear in the shared currency panel above the comparison, numbered **01 / CURRENCIES** in
this tab and **02 / CURRENCIES** in the wishlist tab.

Currency selections are shared between tabs. Existing results keep the currencies
used for that comparison; **Refresh comparisons** applies the current currency-panel
choices to all displayed creator products, including expanded pages. Changing the
baseline preserves existing cursor context and starts new-storefront discovery from
the first page on the next Load more. Use it to
retry incomplete prices after cancellation or a request failure. It reuses fresh
cached prices, so refreshing does not force a new Steam request for every price.
Only one comparison can run per connection; creator examples wait for an active
wishlist comparison, and both use the same paced background worker.

Wishlist and creator results remain separate. The active tab, creator results,
catalog position, and job access token are saved in the same tab's session storage
to survive refresh. Server jobs still expire after an hour or disappear on restart;
completed creator results saved in the tab can remain visible until refreshed.
Prices and NBP rates use the existing shared SQLite cache. Creator catalog pages
are cached in server memory for six hours (up to 128 pages); a failed refresh can
use a labeled stale catalog, except when network access is denied.

Icons come from Steam's avatar CDN, with the bundled official Steam logo as a
fallback. Game artwork continues to use Steam's image CDN. Catalog integration
uses Steam's public storefront JSON/HTML endpoint, verified on 2026-10-02;
it is not a documented Steamworks API contract. Malformed pages fail visibly
instead of executing or forwarding Steam HTML. Each catalog tab has a CSV
download below its catalog list. The CLI does not provide creator browsing.

## Run the command-line prototype

The sample SteamID64 `76561198000000000`, `/id/example` URL, and `your-key`
are placeholders; replace them with your own values. They are not a working demo.

Python 3.10 or newer is required. Numeric SteamID64 values and `/profiles/...`
URLs work without an API key:

```powershell
python .\steam_wishlist_compare.py 76561198000000000
```

## Choose comparison storefronts

The command-line prototype retains Poland (PLN) as its baseline. Select one to
36 supported comparison storefronts with `--regions` after the Steam identifier.
For example, `us` is USD, `de` is EUR and `jp` is JPY; see [the full mapping](STOREFRONTS.md).

```powershell
python .\steam_wishlist_compare.py 76561198000000000 --regions de
python .\steam_wishlist_compare.py 76561198000000000 --regions de us
```

Without `--regions`, the default is `us de`. Selection order is preserved in
results. Currency is determined by the storefront; arbitrary currency/region
pairs, duplicate regions, and the home region are rejected before requests or
cache initialization. The web currency panel additionally lets any supported
storefront become the baseline; it is not inferred from the Steam account. Run with `--help` for command-line help.

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
endpoint. That fallback is not a reliable workaround: the 2026-09-12 research
probe received a store-homepage redirect instead of wishlist JSON. Prefer a
numeric SteamID64 when vanity resolution is not configured.

Do not commit a populated `.env` file. The project does not automatically load
`.env`; `.env.example` only documents the supported variables.

## Rates and comparison methodology

The results include each currency's NBP mid rate and source table, its publication
(`effectiveDate`) date, and whether it came from a live request, cache, or stale
cache. See the [NBP API documentation](https://api.nbp.pl/en.html). The publication
date is separate from the time the application fetched the rate; currencies can
have different publication dates.

The backend loads both latest complete tables A and B upfront for the first
foreign-currency comparison, using one request per table before retries. All rates
are cached, including currencies outside the active comparison. Each table has
its own 24-hour cache age; subsequent comparisons refresh only missing or expired
tables, even when the currently selected rates belong to the other table. Empty
or PLN-only requests need no NBP data and do not preload tables.

Only the active comparison's requested rates are returned in its results. Later
currency selections reuse the cached observations from either table. A table
failure does not block a comparison whose requested rates remain available from
live data or cache. Currency codes absent from both tables fail explicitly; this
does not add Steam storefronts to the interface. Sources distinguish `NBP table A (mid)` and `NBP table B (mid)`.
Use each table's actual publication date rather than assuming it was published
today. API `mid` values already express PLN per one currency unit; do not apply
the multiples used in some printed NBP tables.

Rates are cached for 24 hours. If refresh fails and all needed rates have cached
values, the tool can use them with a visible stale-cache warning. Existing cache
entries migrate automatically; rates without dates are refreshed, or explicitly
shown with an unknown date when refresh fails. Fallback does not reset cache age.

Table writes are atomic: malformed responses cannot partially replace cached
rates. A successful table remains cached even if another required table fails.
Local network permission denial stops retrieval rather than using stale rates.
Cache schema 9 retains each rate's source and records complete-table fetch times;
legacy Table A rows and Steam price observations are preserved on migration.

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

The three visible tabs and the internal owned-library prototype use the same
fixed column names and order (CSV schema 1). Library columns remain present and
blank in the visible tabs; no library request is needed to export.
Download CSV exports all currently loaded results, including products hidden by
filters. A running comparison exports only its completed results so far. There
is one row per game/storefront and one row for each uncompared game. Wishlist
profile attribution is optional and off by default: the `wishlist_profile` column
is always present, but its values remain blank unless enabled. Access tokens are
never exported. Source-specific fields are blank where inapplicable.

Developer and publisher tabs export all checked, non-free products in their
selected catalogs, including uncompared products. Both `developers` and
`publishers` columns are included in every tab, regardless of the display checkbox;
multiple names are separated by semicolons, and unavailable credits are blank.
`catalog_role` and `catalog_name` identify membership. A product belonging to
several selected catalogs has separate rows for each catalog. Unchecked pending
products are omitted during a comparison. Catalog exports retain the currency
choices of their own results; their wishlist-profile values are always blank.
Job credentials are excluded from every export.

The UTF-8 CSV includes original/base/final prices, discounts, prices converted to the baseline currency,
absolute and percentage differences, and exchange-rate provenance. NBP publication
date, original successful retrieval time, and the comparison's rate-check time
are separate fields. Timestamps use UTC. A cache check does not imply a new NBP
request. Older in-memory results without timestamps export blank fields; run a
new comparison after restarting the server to obtain them. PLN identity conversion
has no NBP timestamps. Example exports carry an `example_data` flag identifying the
curated game selection; their prices and exchange rates come from the same live
and cached sources as normal comparisons.

Wishlist comparisons now refresh older price-cache entries missing credits, then
reuse the enriched cache. Already completed results from an older server may still
have blank credits; run another comparison to obtain them. Exporting itself adds
no Steam or NBP requests.

CSV is intended for spreadsheets and analysis; numeric values use decimal points,
without currency symbols, grouping, or display rounding. Booleans are `true`/`false`.
Unknown or inapplicable values are empty fields; zero remains numeric zero. The file
has a UTF-8 BOM, comma separators, quoted fields, and CRLF row endings. Quotes,
commas, and line breaks inside text are preserved. Credit names and comparison
storefronts/currencies are joined with `; ` in the order received.
Untrusted text starting with spreadsheet formula characters is prefixed with an
apostrophe. JSON could preserve nested results more naturally, but is not currently
offered. Export is generated locally in the browser without additional requests.

### Shared CSV schema

The original 29 price columns keep their names and positions. Profile, catalog,
and credit columns are now fixed across tabs, followed by additional metadata.
Consumers should read fields by header name and use `csv_schema_version` (`1`).
`source_tab` is `wishlist`, `library`, `developer`, or `publisher`. The columns below appear
in exactly this order, reading each row from left to right:

| Fields | Meaning |
| --- | --- |
| `exported_at_utc`, `example_data`, `game_id`, `game`, `status` | Export time, example flag, Steam App ID, title, and `compared` or the skip category. |
| `storefront`, `currency`, `final_price`, `base_price`, `discount_percent` | Observed storefront code and its original-currency final/base prices and discount. Blank for uncompared products. |
| `rate_to_pln`, `rate_publication_date`, `rate_retrieved_at_utc`, `rate_checked_at_utc`, `rate_source`, `rate_cache_status` | The row currency's NBP quote and provenance. PLN uses an identity rate with no NBP dates. |
| `final_price_baseline`, `baseline_difference`, `baseline_difference_percent`, `different_regional_discounts`, `price_provenance` | Converted final price, product-wide difference against the cheapest alternative, discount mismatch, and aggregate price-request sources. |
| `baseline_storefront`, `baseline_currency`, `rate_to_baseline`, `baseline_rate_to_pln`, `baseline_rate_publication_date`, `baseline_rate_retrieved_at_utc`, `baseline_rate_checked_at_utc`, `baseline_rate_cache_status` | Baseline identity, the row conversion factor, and the second NBP conversion leg. |
| `wishlist_profile`, `catalog_role`, `catalog_name`, `developers`, `publishers` | Opt-in wishlist attribution, catalog membership, and both credit lists. Wishlist catalog fields and catalog profile values are blank. |
| `csv_schema_version`, `source_tab`, `catalog_id`, `steam_url`, `comparison_storefronts`, `comparison_currencies`, `wishlist_loading_order`, `checked_index` | Schema/source identifiers, catalog ID, Steam product link, alternatives used by the results, wishlist loading order, and check position within the job. |
| `baseline_final_price`, `cheapest_alternative_storefront`, `cheapest_alternative_currency`, `cheapest_alternative_final_price_baseline`, `baseline_is_cheaper_or_equal` | Baseline price and cheapest-alternative details repeated on each observed-storefront row. Ties retain the first selected alternative. |
| `storefront_difference_baseline`, `storefront_difference_percent`, `base_price_baseline`, `storefront_price_source`, `baseline_rate_source` | Difference against this row's alternative, converted base price, individual price source, and baseline rate provider. Row-specific differences are blank on baseline rows. |
| `skipped_reason`, `skipped_storefront`, `skipped_retryable`, `cache_hits`, `stale_cache_hits`, `live_price_requests`, `developers_known`, `publishers_known` | Controlled failure label, affected region, retry flag, product-level lookup counts, and whether each credit list was supplied. |
| `library_profile`, `library_loading_order` | Additive columns at the end of the shared schema. Opt-in profile and `name`/`steam` library loading order; blank on other tabs. Existing columns retain their positions. |

Both difference types use `(baseline final - alternative final)`, in the baseline
currency. Percentages divide that difference by the corresponding alternative
final and multiply by 100. Negative means cheaper in the baseline. Percentages
are blank when the reference is zero. Product-wide differences repeat across
storefront rows; row-specific differences compare each alternative separately.
An uncompared row contains no partial regional prices, because those observations
are not retained in the comparison result. Available credits and failure metadata
are still included. `developers_known`/`publishers_known` distinguish an empty
reported list (`true`, blank names) from missing metadata (`false`, blank names).


## Storefront thumbnails

Each title links to Steam with a lazy-loaded header thumbnail from Steam's image
CDN. Fixed image slots and reused rows avoid layout shifts; unavailable artwork
shows a neutral fallback. Hovering over either the artwork or title shows the
Steam App ID. Images use app IDs already in the results, so there are
no additional regional price requests. Browsers fetch artwork directly from
`shared.akamai.steamstatic.com` without a referrer. The image policy allows only
that external host.


## Readability and sorting

Wishlist title search sits in the second table-header row, below **Game name**
and beside the individual currency labels. Its bordered
field fills the game column on desktop and the visible table width on narrow
screens. It filters loaded titles without fetching more data; clear it to restore
matching results under the current filters and sorting. Name sorting remains a
separate button above search.

Foreign final prices use 16px text. Column headings identify Game name and
the baseline storefront. Difference offers independent absolute and percentage sort buttons;
repeated clicks cycle lowest to highest (A–Z), highest to lowest (Z–A), then
original loading order. Switching to another column starts ascending. Missing
numeric values stay last in either direction. The enlarged arrow lights its
top 40% for ascending or bottom 40% for descending with a light-blue gradient;
neither end lights when unsorted. This replaces Reset sorting. Uncompared
shows contextual help explaining missing prices, failed requests, and the separate
availability toggle. Storefront labels remain geographic: currency alone does not
establish identical regional offers.


## Baseline and comparison selection

Select a baseline in the searchable currency panel above the comparison and one to 36 other currencies.
The baseline cannot also be an alternative. Select all chooses every other
representative storefront; Clear removes alternatives. Search does not deselect
hidden choices. The browser and API use the same 37-currency registry. See
[supported storefronts and table behavior](STOREFRONTS.md) for the complete mapping,
pinned columns, synchronized horizontal scrolling and amount-unit validation.

Selection cards show circular flags alongside currency/country text. EUR uses
the EU flag; its prices still come from Germany. The flags load from one locally
bundled SVG sprite and need no external flag service. Named summaries use
"USD and EUR" for two alternatives and "USD, EUR, AUD, and CAD" for four;
more than four alternatives use the existing storefront-count summary.

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
wins over a previously hidden currency. Up to all 36 alternatives may be selected.
Restoring a saved comparison replaces the preferences with that run's selections.
Regression tests exercise actual change handlers, repeated switches, explicit
replacement/deselection, welcome captions, busy state, and saved restoration.

## Backend currency changes after loading

The browser uses this endpoint for wishlist/example updates. Programmatic clients
can submit a same-origin JSON POST to `/api/jobs/{id}/currencies` with the source
job's bearer token and a body such as `{"home":"us","regions":["pl","gb"]}`.
The 37 supported storefronts and one-to-36 alternatives limit apply; omitted
`home` defaults to Poland, as for initial comparisons. Additional fields, including
new product IDs or loading orders, are rejected.

Only unexpired jobs in `complete` or `partial` state can be used. The response is
202 with a new `id`, new `token`, and `previous_job_id`. Poll and cancel the new job
through the existing job routes using its new token. The source result is unchanged
and remains available until its normal expiry. Clients should keep it displayed
while the new job runs, then adopt the new result and currencies together. A failed
or cancelled attempt can be retried by submitting against the original completed
job. Concurrent currency changes for the same chain of comparisons are rejected,
even from another connection; existing owner and capacity limits apply. Sequential comparisons have no
per-minute start limit; Steam requests still share the 1.5-second pacing gate.

The operation reuses the exact loaded selection and emitted game order. It does
not reload a wishlist, owned library, catalog page or creator search. Catalog
membership and page cursors are retained for that job. To combine multiple loaded
catalog pages, the frontend submits their unique app IDs through the existing
`/api/creator-jobs` endpoint with `mode: "products"`, home and regions; it keeps
group membership and pagination state locally. That path also skips discovery and
reuses the shared caches. Page offsets must retain their discovery storefront context;
later pagination in another storefront restarts discovery and deduplicates loaded
products. See the implemented frontend behavior in [ROADMAP.md](ROADMAP.md).
Owned-library
currency changes remain behind the same internal feature flag.

Initial loading fetches only selected Steam countries. Successful regional default
prices, metadata and best offers are retained in the shared cache even when another
region prevented a game comparison. Currency-change jobs reuse fresh observations
and fetch missing or expired observations only for their selected countries.
Switching back to fresh cached countries makes no Steam requests. A stale best offer
can refresh independently of a fresh default price. Exchange rates use their normal
cache rules; a fresh Steam cache alone does not imply zero NBP requests.
Cancellation retains completed cache writes. Normal pacing, retries, stale fallback,
provenance and local-network-denial handling remain in effect.

Loaded selection/order and profile attribution are private, expiring server memory;
the shared cache stores no profile-to-game mapping. Server restart or source-job
expiry requires a new initial wishlist comparison for currency changes; the
browser submits it automatically when Update currencies encounters an expired
source, retaining displayed results until the replacement finishes. Catalog
updates use saved loaded IDs. The frontend preserves view settings and restores
displayed/pending state separately.

## Continuing development

The owned-library prototype is retained but hidden behind an internal flag in
0.5.0-beta. Authenticated live testing remains TODO; see the
[development roadmap](ROADMAP.md) before enabling it. The available wishlist,
developer, and publisher features retain the shared CSV and product credits.

Follow the preview lifecycle guidance above and inspect the repository state
before continuing. Git and the [changelog](../CHANGELOG.md) record completed work;
the [roadmap](ROADMAP.md) lists future directions. Read
[docs/STEAM_SORTED_WISHLIST_API.md](STEAM_SORTED_WISHLIST_API.md) before
changing wishlist retrieval or adding Steam-compatible loading orders.

### Product credits

Your wishlist shows both **Developer:** and **Publisher:** beneath each game's
artwork/title, using the same small, muted text as the catalog tabs. Role labels
and names share a fluid grid, so both name lists align and wrapped names stay in
their own column. See [text and localization decisions](TEXT_AND_LOCALIZATION.md)
for wording and future translation guidance. All reported
names appear, including multiple developers and co-publishers. Missing or empty
credits show Unavailable; pending rows show Loading…. Credit text also appears
on example comparisons and skipped results when metadata is available.
Existing results from an older server show Unavailable until a new comparison
supplies their missing credits. Sorting, filtering, and displaying credits do not
fetch additional prices or metadata. Both lists are already included in CSV.

The Developers tab shows publishers, and the Publishers tab shows developers.
By default, credits appear as small text below each product title. Check
**Show publisher column** / **Show developer column** above search to move the
credits into a separate labeled column. All reported names appear, including
co-publishers. Each tab remembers its display mode;
missing credits are labeled Unavailable. Credits come from the same Steam
appdetails response as prices and are cached with them. Older saved catalog
comparisons refresh once to obtain credits.


## Batched retrieval and Steam best purchase offers (0.6.0-beta)

The web app uses one batch pipeline for every list size. Default prices come from
appdetails price-only requests, and StoreBrowse supplies metadata and Steam's
selected purchase option. Each request has one country context. The existing
selection limit is now one to 36 alternatives, using one representative country
for each of the 37 supported live currencies.

The checkbox sits directly above the comparison table in each tab. Wishlist
groups it with Show unavailable products and the game filters in one wrapping
row. The blue circular i button after its label opens an explanation without
changing the checkbox. Close it with its circular X, the i button or Escape.
Clicking elsewhere leaves it open. The bubble opens centered on the i, adjusting
near viewport edges, and scrolls with the page. Its setting is shared across tabs
and survives reload in the same browser tab.

Enable **Show Steam's best purchase offers alongside game prices** to reveal a
separate set of prices and regional differences. Both datasets are fetched during
loading, so changing this checkbox requires no network request. The choice survives
refresh in the same browser tab and applies to all comparison tabs. Older saved
results need a new comparison to populate best offers. Default game offers still
drive filters, sorting, counts, and catalog statistics; the secondary offer section
has its own difference and color. Unavailable default rows remain subject to the
existing Show unavailable products control.

Each secondary offer identifies its package or bundle and links to that purchase
option. Anonymous prices assume no existing ownership. Steam may choose different
editions/bundles between countries, and personalized eligibility can change the
checkout price. Recurring subscription options are not compared. StoreBrowse does
not supply an explicit currency code in these responses: currency is attributed
to the requested supported storefront and that basis is retained in tooltips/CSV.

Discounts prefer Steam's percentage when it matches the regular/current-price relation.
Only missing or inconsistent percentages are calculated as
`(regular price - current price) / regular price × 100`, rounded down to whole
percentage points and marked ≈ (for example, ≈−33%). Calculated sales below 1%
show ≈0%. Hover over a discount badge to see whether Steam supplied the percentage
or the app calculated it. CSV appends `discount_calculated` and `best_offer_discount_calculated`
flags so consumers can distinguish calculated percentages from Steam's values. Compliance-only references such as a recent low are not
used. Regular bundle discounts remain unavailable when only component savings or
ambiguous reference prices are supplied. This does not prevent comparing current
bundle prices. Default game prices remain separately available with their own base.

CSV schema 1 gains additive `best_offer_*` fields after existing library columns:
status, kind, ID, name, original-currency final price, currency, currency basis,
regular price, discount percentage, converted price, source, comparison difference,
and percentage difference. Exports always include these fields regardless of the
checkbox. Missing values stay blank. For an uncompared default game with best-offer
observations, one row per requested region retains those observations separately.
No extra request is made when exporting.

The legacy `live_price_requests` field now counts physical attempts for default
price, metadata and best-offer batches. Shared attempts are attributed once to the
first emitted game in a window; name-prefetch attempts join the first window. A
zero on a later row does not imply that row came from cache. Cache-hit fields count
item-country observations. These per-game fields repeat in regional CSV rows;
do not sum them across those duplicates. Wishlist/NBP requests are counted
separately in the performance report, not this legacy per-row field.

Cache schema 8 tracks calculated-discount provenance, retains existing prices/rates and adds independent metadata (24 h)
and best-offer (15 min) observations. Default-price TTLs remain one hour normally,
15 minutes on sale, one hour for missing prices and six hours for unavailable apps.
Metadata/offer refreshes do not reset default-price age. Partial and cancelled jobs
retain completed observations. Temporary-error stale fallback is labeled; local
network denial stops work. Metadata source is included in result data and wishlist
credit tooltips. No wishlist/profile ownership mapping is stored in the shared cache.

Programmatic configuration uses `JobManager(batch_policy=BatchPolicy(...))`.
Defaults: `metadata_size=100`, `price_size=100`, `url_bytes=6000`,
`recovery_calls=7`, `attempt_budget=21`. The latter ceilings apply to each planned
batch and all recovery children, including retries. Throttling does not split
batches; Retry-After also delays subsequent batches after a final failed attempt.
These settings are operational bounds, not published Valve guarantees.

See [measured performance](STEAM_PRICE_PERFORMANCE.md) and
[implemented design](STEAM_PRICE_BATCHING_PLAN.md). Changing loaded-result currencies
is implemented for completed wishlist/example and catalog comparisons; the
remaining layout and performance work is described in [ROADMAP.md](ROADMAP.md).


Discount percentage preference: retain Steam's reported percentage when it agrees
with the known regular/current price relationship, allowing whole-percent rounding
or truncation and one minor unit of price rounding. Calculate a replacement only
when the percentage is missing or inconsistent. A known regular price is required;
compliance-only references and ambiguous bundle bases still remain unavailable.
The same rule applies to live default prices, cached prices and eligible best offers.
Previously cached calculated percentages cannot recover an overwritten upstream
value; ordinary cache expiry refreshes them without extra requests for this change.
