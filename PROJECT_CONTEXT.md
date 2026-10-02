# Steam Currency Comparer — development handoff

Updated: 2026-10-02. This is a current-state summary, not a change log.

## Start here

Read AGENTS.md for collaboration preferences and README.md for usage and
methodology. Inspect Git status and the implementation before changing anything.
Use Git history for historical details; do not repeat the development history.
Continue with the user's next request rather than inventing a new feature or
deploying the app. Local-server lifecycle and network-permission error handling
have been addressed; see the operational notes below.

## Publication and version

README.md is the public-facing introduction and installation guide, with direct
virtual-environment commands for Windows and macOS/Linux. Detailed existing usage
and implementation notes are retained in docs/USAGE.md. Documentation explicitly
labels sample profile identifiers as placeholders. The public display name is Steam Currency Comparer. Existing Python package,
script names, environment variables, and cache paths retain their original names
for compatibility.

Current version: `0.1.0-beta.1`, defined in `steam_price_polisher/version.py`.
The server renders it into the header and returns it from `/api/health`.
The source beta was pushed to GitHub on 2026-09-23. No release tag was created
during that publication; there are no tags in the current local repository.
README screenshots live in docs/images/ and show the built-in seven-game live
example, captured on 2026-09-23 without a personal profile. The title and version
badge have been checked at desktop and 320/390 CSS-pixel mobile widths. Mobile
headers put the version badge on its own row. The GitHub repository is
https://github.com/instant-results/steam-currency-comparer. Source publication
is separate from hosting the app or creating a tagged GitHub release.

## Product and current behavior

A local web app compares public Steam wishlist and creator-catalog prices across international storefronts; eventual public hosting
is intended but has not happened. Use plain, direct UI language describing regional prices and exchange rates.

- Select a baseline from PLN/Poland, USD/United States, EUR/Germany, NOK/Norway,
  or GBP/United Kingdom, plus one or two other currencies. The baseline is
  selected manually, not derived from the Steam profile. Default: PLN vs USD/EUR.
- The interface has Your wishlist and Developers & publishers tabs with shared
  currency settings and separate saved results. The wishlist presents three numbered steps: wishlist input, currency choices,
  and comparison results. The Steam profile field and primary/example actions
  occupy the full-width first row; the currency sidebar is reserved for baseline
  and comparison choices.
  The shared currency panel is step 02 in the wishlist tab and step 01 in the
  creator tab, where no profile input is needed.
- The wishlist row selects the initial loading order: personal priority
  (default, lowest number first), date added (newest first), or name (A-Z).
  Missing metadata remains stable at the end. Alphabetical order may prefetch
  baseline details to obtain names, then reuses those lookups without duplicate
  baseline requests. The selected order persists with refresh and retry.
- Baseline conflicts temporarily hide comparison selections. Switching to a
  non-conflicting baseline restores them. Explicit checkbox edits replace the
  remembered choices. Saved-job restoration restores that run's selections.
- The welcome caption follows sidebar choices. Existing results retain their
  own baseline when the user edits the form for a future run.
- Results append in the selected loading order using stable row elements. Game name,
  baseline price, absolute difference, and percentage difference can be sorted.
  Reset sorting restores loading order without restarting or changing filters.
- Table column headers align horizontally and vertically with row data:
  "GAME NAME" offsets for the artwork thumbnail slot to align with game titles,
  the baseline price header aligns with numerical prices, "OTHER STOREFRONTS"
  and "DIFFERENCE" share the centered primary header baseline, while their
  secondary conversion and sort labels sit directly beneath without affecting
  that centering. All headers share uniform typography and prominence.
- Unavailable products are hidden by default. Uncompared includes missing prices
  and technical failures, subject to the separate unavailable-products toggle.
- Each regional price retains its own base price, final price, and discount.
  Unequal known discounts receive a badge and filter; unknown is not zero.
- Differences use the cheapest selected alternative in baseline currency.
  A zero reference makes the percentage unavailable.
- Price provenance (cached, live, stale) is displayed individually on hover:
  standalone for the baseline price and alongside the converted price calculation
  for foreign storefronts.
- Lazy-loaded Steam header thumbnails have fixed slots and a missing-image
  fallback. Hovering over either a game's artwork or title shows its Steam App ID.
- CSV exports all loaded results, regardless of filters, with optional profile
  attribution off by default. It includes both exchange-rate legs and their
  publication, retrieval, and check times; tokens are never exported.
- Start, Cancel, and example actions sit in the full-width wishlist row. Profile,
  baseline, comparison currencies, and loading order are retained with the saved
  job in the same tab. Example mode compares a curated
  7-game wishlist (including The Witcher 3) using live Steam prices and official NBP exchange rates.

- One visible heading row sits above all creator groups, aligned with their shared
  table columns. Horizontal scrolling stays synchronized on narrow screens;
  each creator table retains visually hidden column headings for screen readers.
  Each creator's icon/name appears in a full-width row above its games, alongside
  per-foreign-storefront mean percentage differences (equal product weight,
  unrounded calculations, positive = pricier in baseline), medians, and sample counts.
  Median uses the middle sorted difference, or the mean of the middle two for an
  even sample size; it shares the average's eligible sample.
  Missing/pending/free/zero-reference products are excluded from averages. Coverage
  and cheaper/equal, pricier, uncompared, and pending counts cover loaded products
  only. Statistics reuse results and their currency settings, updating on load,
  restoration, and refresh. Paid DLC/soundtracks count alongside games.
  Desktop statistics align with fixed foreign-price slots using shared column
  widths. A subtle vertical divider separates baseline and foreign prices.
  Narrow creator panels stack statistics and share scrolling for 760px tables.
  Opening the creator tab automatically compares three curated games each from
  Supergiant Games, CD PROJEKT RED, and Devolver Digital. Icons use the Steam avatar
  CDN with an official Steam-logo fallback. Load more appends pages of up to 12
  products, including paid DLC/soundtracks, without duplicating featured examples.
  Free products (including demos) are removed after checking Steam's free flag or
  a zero baseline price; missing prices alone do not imply free. The free flag is
  persisted in the price cache (schema version 5); old missing-price cache entries
  are rechecked on web comparisons. Refresh old saved creator results to classify
  free products. Free-only pages advance normally and can require another Load more.
  Refresh compares all displayed products with the current form currencies;
  expanded pages otherwise retain the existing run's currencies. A baseline change
  restarts catalog pagination while retaining displayed products. Unavailable
  products stay visible. Both tabs share the paced worker, owner limits, and price
  cache; creator examples wait for an active wishlist. Search is postponed.
  Creator results, catalog cursors, active tab, and job token use separate tab
  session storage. Saved completed creator results can outlive server jobs and
  need an explicit refresh for a new price check. CSV stays on the wishlist tab.

## Architecture and constraints

Python WSGI backend, vanilla HTML/CSS/JavaScript frontend; no frontend build step.

- serve_web.py: loopback preview on port 8765.
- steam_price_polisher/web_app.py: validated API, private bounded jobs, worker,
  result metadata, and cross rates.
- web/app.js, web/index.html, web/app.css: UI state, rendering, CSV, and styling.
- creators.py and web/creators.js: featured creator registry, bounded catalog-page
  cache, defensive Steam HTML parsing, and independent creator-tab state. API:
  GET /api/creators, POST /api/creator-jobs; results/cancel use existing tokenized
  job routes. Catalogs use Steam's public ajaxgetfilteredrecommendations endpoint;
  this storefront contract is undocumented and needs ongoing compatibility checks.
  Catalog cache: six hours, up to 128 pages in memory, keyed by creator/region/cursor.
  Regional comparisons retain the existing sale-price freshness and rate metadata.
- configuration.py: five storefront/currency pairs and selection validation.
- analysis.py, comparison.py: per-game workflow and pure comparison arithmetic.
- steam_access.py, price_service.py: Steam retrieval and price-cache handling.
- exchange_rates.py, cache.py: NBP rates and SQLite persistence.
- request_policy.py, http_client.py: pacing, retries, and secure HTTP.
- event_log.py: structured local diagnostics, rotation, job correlation, and safe metadata.
- steam_wishlist_compare.py: CLI, still using Poland as baseline.
- DEPLOYMENT.md: hosting guidance; consult before any deployment work.
- docs/STEAM_SORTED_WISHLIST_API.md: implementation-ready research handoff for
  Steam's richer sorted/filtered wishlist service and additional loading orders.

NBP quotes PLN per unit. Convert A to baseline B using rate[A] / rate[B],
with PLN = 1. Preserve both source dates and cache provenance. Regional sale
metadata comes with the price response; inspecting discounts costs no extra
price request. Do not infer other regions' discounts from the baseline.

One background worker paces sequential Steam requests, using cached results.
Web prices normally expire after one hour, known sales after 15 minutes, and
exchange rates after 24 hours; labeled stale fallback is possible. Missing
baseline prices can skip alternative requests. Web wishlists are public-only,
up to 1,000 games. Jobs expire and are lost on server restart; cached prices remain.

Keep cache files, local wishlists, cookies, and keys out of Git. The web app does
not use CLI cookies or local wishlist files. HTTPS verification must remain enabled.

## Local server lifecycle and network access

The preview binds exclusively on Windows and rejects duplicate listeners,
including legacy servers using address reuse. It handles interrupt/termination
signals, checks the original parent process for exit, and closes the listener
through context-manager cleanup. Slow HTTP clients run on daemon request threads.
Keep the launching terminal alive; use the WSGI factory for managed deployments.
`--port` selects a loopback port (0 requests an available temporary port).

Follow docs/USAGE.md lifecycle checks before and after starts/restarts. Repeatable subprocess tests cover shutdown,
parent exit, duplicate launches, and immediate reuse of the released port.

Launch live previews with outbound network access. OS socket permission denial
(including Windows 10013) becomes a non-retryable `network_access_denied` error,
with sanitized guidance to restart with outbound access. This propagates through
wishlist/vanity lookup, regional prices, and exchange rates. Permission denial
stops the job, including alphabetical prefetch; stale rates do not conceal it.
HTTP 403, TLS errors, and local file permission errors remain distinct.

## Wishlist API research handoff

The 2026-09-12 probe of `IWishlistService/GetWishlistSortedFiltered/v1` returned the
complete wishlist in a requested Steam sort order while enriching a selected
range with Store Browse name, release, and review data. This could add Release
Date, Top Selling, and Review Score loading orders and remove alphabetical name
prefetching. The historical `/wishlistdata/?p=...` fallback redirected to the
store homepage during anonymous verification and must not be treated as a
working rich-data contract. No integration has been implemented. See
`docs/STEAM_SORTED_WISHLIST_API.md` for the observed schema, risks, decisions,
file map, tests, and acceptance criteria.

## Diagnostic logging

The preview and WSGI factory configure a dedicated event logger. Per-process
JSON Lines files live under the data directory's `logs/events-<PID>.jsonl`, with
2 MiB rotation and three backups per process. Old process logs remain until
removed. Git ignores event files, including rotations. INFO covers lifecycle
and failures; `STEAM_PRICE_POLISHER_LOG_LEVEL=DEBUG` adds request successes and
cache provenance to files while console output stays at INFO.

Context-local job IDs connect lifecycle, request, and cache events across worker
execution. Only allowlisted metadata is recorded: no credentials, profiles,
game lists/prices, request URLs/headers/bodies, raw exception text, or local
absolute paths. Unexpected failures include type and project code location.
File logging failures fall back to console diagnostics without stopping jobs.
See docs/USAGE.md for diagnostic configuration. The CLI does not automatically
configure file logging.

## Run and verify

From the repository root:

```powershell
python -m unittest discover -q
node --test tests/test_web_render.cjs
node --check web/app.js
node --check web/creators.js
git diff --check
```

After verifying that port 8765 is clear, start the preview separately with
`python serve_web.py`, then confirm http://127.0.0.1:8765/api/health. Static
changes need a browser refresh; backend changes need a verified clean restart,
which clears in-memory jobs. Avoid triggering full live wishlists for routine
tests.

Verified locally on 2026-10-02: 108 Python tests and 25 frontend tests pass;
both frontend scripts also pass syntax checks. Live creator directory/catalog
probes and featured regional comparisons were verified for this extension;
the sorted wishlist API has not been re-probed. Tests cover
configuration combinations, cross rates, API validation, caching/failures,
render stability, wishlist loading order, filtering/sorting, CSV, thumbnails,
creator parsing/pagination/cache/validation, independent tab results/restoration,
and selection restoration.
Frontend tests use a minimal DOM harness; they do not establish browser visual
correctness. Use targeted UI verification when needed.

## Open work and decisions

- Future hosting means a free public website with a few non-intrusive ads,
  potentially covering costs. No paid tiers, billing, or accounts have been
  requested. See DEPLOYMENT.md for service gaps; no hosting or ads are implemented.
- The sorted wishlist API remains research only. Creator search is postponed;
  the creator directory is curated. Do not start either integration without a request.
- No license file or GitHub Actions workflow is tracked. Licensing and CI remain
  open decisions; do not describe the repository as licensed open source.
- The README screenshots show a partial results view and an overview captured
  from the live curated example. They contain no personal profile. They are
  historical illustrations, not today's price quotes.
- A pre-publication local history scan found no apparent real credentials or the
  user-specified personal Steam profile. Matches were placeholders/test data;
  authorship uses a GitHub noreply address. This was a pattern-based local scan,
  not a security guarantee. Do not add personal identifiers to documentation.

## Git handoff

`main` tracks `origin/main` at
https://github.com/instant-results/steam-currency-comparer.git. The last confirmed
push was `9dbc37d` on 2026-09-23, covering branding/versioning, separate tests,
API research, public documentation, and screenshots. At the start of this
2026-10-02 documentation refresh, local HEAD and the local `origin/main` tracking
ref both pointed there and the working tree was clean. The remote was not fetched
again for this refresh; inspect actual status before starting new work.

On this Windows machine, the successful push used
`git -c http.sslBackend=schannel push -u origin main` to use the Windows trust
store. HTTPS verification remained enabled; never disable it to resolve a
certificate error. Sandbox restrictions can also require approved network/Git
write access.

The creator-tab implementation and the earlier Markdown refresh are uncommitted.
The app version has not been bumped; no tag or deployment was created.
Follow AGENTS.md for commit reminders;
commit/push only when authorized for the current work, and keep feature and test
changes in separate coherent commits. Do not infer that an old preview is still
running: check the listener and health response before starting another server.
