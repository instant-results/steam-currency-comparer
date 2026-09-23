# Steam Currency Comparer — development handoff

Updated: 2026-09-23. This is a current-state summary, not a change log.

## Start here

Read AGENTS.md for collaboration preferences and README.md for usage and
methodology. Inspect Git status and the implementation before changing anything.
Use Git history for historical details; do not repeat the development history.
Continue with the user's next request rather than inventing a new feature or
deploying the app. Local-server lifecycle and network-permission error handling
have been addressed; see the operational notes below.

## Publication preparation

README.md is the public-facing introduction and installation guide, with direct
virtual-environment commands for Windows and macOS/Linux. Detailed existing usage
and implementation notes are retained in docs/USAGE.md. Documentation explicitly
labels sample profile identifiers as placeholders. The public display name is Steam Currency Comparer. Existing Python package,
script names, environment variables, and cache paths retain their original names
for compatibility.

Current version: `0.1.0-beta.1`, defined in `steam_price_polisher/version.py`.
The server renders it into the header and returns it from `/api/health`.
The first beta is being prepared; no release tag has been created.
README screenshots live in docs/images/ and show the built-in seven-game live
example, captured on 2026-09-23 without a personal profile. The title and version
badge have been checked at desktop and 320/390 CSS-pixel mobile widths. Mobile
headers put the version badge on its own row. The GitHub repository is
https://github.com/instant-results/steam-currency-comparer. Source publication
is separate from hosting the app or creating a tagged GitHub release.

## Product and current behavior

A local web app compares public Steam wishlist prices across international storefronts; eventual public hosting
is intended but has not happened. The interface uses plain, direct, functional language describing
regional price comparisons and exchange rates. All AI-generated marketing taglines, faux-edgy slogans,
and dramatic fragment copy have been eliminated in favor of clear technical prose.

- Select a baseline from PLN/Poland, USD/United States, EUR/Germany, NOK/Norway,
  or GBP/United Kingdom, plus one or two other currencies. The baseline is
  selected manually, not derived from the Steam profile. Default: PLN vs USD/EUR.
- The interface presents three numbered steps: wishlist input, currency choices,
  and comparison results. The Steam profile field and primary/example actions
  occupy the full-width first row; the currency sidebar is reserved for baseline
  and comparison choices.
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

## Architecture and constraints

Python WSGI backend, vanilla HTML/CSS/JavaScript frontend; no frontend build step.

- serve_web.py: loopback preview on port 8765.
- steam_price_polisher/web_app.py: validated API, private bounded jobs, worker,
  result metadata, and cross rates.
- web/app.js, web/index.html, web/app.css: UI state, rendering, CSV, and styling.
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

Follow README.md checks before and after starts/restarts. Repeatable subprocess tests cover shutdown,
parent exit, duplicate launches, and immediate reuse of the released port.

Launch live previews with outbound network access. OS socket permission denial
(including Windows 10013) becomes a non-retryable `network_access_denied` error,
with sanitized guidance to restart with outbound access. This propagates through
wishlist/vanity lookup, regional prices, and exchange rates. Permission denial
stops the job, including alphabetical prefetch; stale rates do not conceal it.
HTTP 403, TLS errors, and local file permission errors remain distinct.

## Wishlist API research handoff

Steam's current `IWishlistService/GetWishlistSortedFiltered/v1` can return the
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
See README.md for usage. The CLI does not automatically configure file logging.

## Run and verify

From the repository root:

```powershell
python -m unittest discover -q
node --test tests/test_web_render.cjs
node --check web/app.js
git diff --check
```

After verifying that port 8765 is clear, start the preview separately with
`python serve_web.py`, then confirm http://127.0.0.1:8765/api/health. Static
changes need a browser refresh; backend changes need a verified clean restart,
which clears in-memory jobs. Avoid triggering full live wishlists for routine
tests.

Last verified: 99 Python tests and 20 frontend tests, all passing. Tests cover
configuration combinations, cross rates, API validation, caching/failures,
render stability, wishlist loading order, filtering/sorting, CSV, thumbnails,
and selection restoration.
Frontend tests use a minimal DOM harness; they do not establish browser visual
correctness. Use targeted UI verification when needed.

## Git handoff

The integration branch is `main`. Structured logging implementation, regression
tests, and documentation are versioned in separate commits. Use Git history
for commit details.

Inspect actual Git status rather than relying on this snapshot. Follow AGENTS.md
for reminders and separate feature/test commits when committing authorized work.
