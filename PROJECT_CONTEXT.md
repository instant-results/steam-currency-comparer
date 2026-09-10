# Steam Prices Polisher — development handoff

Updated: 2026-09-10. This is a current-state summary, not a change log.

## Start here

Read AGENTS.md for collaboration preferences and README.md for usage and
methodology. Inspect Git status and the implementation before changing anything.
Use Git history for historical details; do not repeat the development history.
There is no outstanding implementation request at this handoff. Continue with
the user's next request rather than inventing a new feature or deploying the app.

## Product and current behavior

A local web app compares public Steam wishlist prices across international storefronts; eventual public hosting
is intended but has not happened. The interface uses plain, direct, functional language describing
regional price comparisons and exchange rates. All AI-generated marketing taglines, faux-edgy slogans,
and dramatic fragment copy have been eliminated in favor of clear technical prose.

- Select a baseline from PLN/Poland, USD/United States, EUR/Germany, NOK/Norway,
  or GBP/United Kingdom, plus one or two other currencies. The baseline is
  selected manually, not derived from the Steam profile. Default: PLN vs USD/EUR.
- Baseline conflicts temporarily hide comparison selections. Switching to a
  non-conflicting baseline restores them. Explicit checkbox edits replace the
  remembered choices. Saved-job restoration restores that run's selections.
- The welcome caption follows sidebar choices. Existing results retain their
  own baseline when the user edits the form for a future run.
- Results append in discovery order using stable row elements. Game name,
  baseline price, absolute difference, and percentage difference can be sorted.
  Reset sorting restores discovery order without restarting or changing filters.
- Table column headers align horizontally and vertically with row data:
  "GAME NAME" offsets for the artwork thumbnail slot to align with game titles,
  the baseline price header aligns with numerical prices, "OTHER STOREFRONTS"
  aligns vertically on the primary header baseline with converted subtext beneath,
  and all headers share uniform typography and prominence.
- Unavailable products are hidden by default. Uncompared includes missing prices
  and technical failures, subject to the separate unavailable-products toggle.
- Each regional price retains its own base price, final price, and discount.
  Unequal known discounts receive a badge and filter; unknown is not zero.
- Differences use the cheapest selected alternative in baseline currency.
  A zero reference makes the percentage unavailable.
- Price provenance (cached, live, stale) is displayed individually on hover:
  standalone for the baseline price and alongside the converted price calculation
  for foreign storefronts.
- Lazy-loaded Steam header thumbnails have fixed slots and a missing-image fallback.
- CSV exports all loaded results, regardless of filters, with optional profile
  attribution off by default. It includes both exchange-rate legs and their
  publication, retrieval, and check times; tokens are never exported.
- Start and Cancel share a sidebar slot. Profile, baseline, and comparisons are
  retained with the saved job in the same tab. Example mode compares a curated
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
- steam_wishlist_compare.py: CLI, still using Poland as baseline.
- DEPLOYMENT.md: hosting guidance; consult before any deployment work.

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

## Run and verify

From the repository root:

```powershell
python serve_web.py
python -m unittest discover -q
node --test tests/test_web_render.cjs
node --check web/app.js
git diff --check
```

Preview: http://127.0.0.1:8765/. Check whether it is already running before
starting another process. Static changes need a browser refresh; backend changes
need a restart, which clears in-memory jobs. Avoid triggering full live wishlists
for routine tests.

Last verified: 73 Python tests and 20 frontend tests, all passing. Tests cover
configuration combinations, cross rates, API validation, caching/failures,
render stability, filtering/sorting, CSV, thumbnails, and selection restoration.
Frontend tests use a minimal DOM harness; they do not establish browser visual
correctness. Use targeted UI verification when needed.

## Git handoff

Branch at handoff: main. Latest implementation commits:
- 546fcb5: Align table column headers horizontally and vertically with matching typography.
- 4e9f010: Display price provenance on hover and remove aggregate capsule labels.

The working tree is clean. Inspect actual Git status rather than relying on this snapshot. Follow AGENTS.md for reminders and separate feature/test commits when committing authorized work.
