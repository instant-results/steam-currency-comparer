# Steam Currency Comparer — development handoff

Updated: 2026-10-18. Current state, not a change log.

## Start here

Read AGENTS.md, README.md, and docs/USAGE.md, then inspect Git status/code.
Owned-library code is retained in 0.5.0-beta but hidden/disabled by default.
Its authenticated live API-key testing is deferred until Steam Guard/key setup
is available. See docs/ROADMAP.md for the TODO checklist. The stage is not complete.
Current branch: codex/steam-price-batching. Steam price batching with an optional separate best-offer comparison is
the selected next stage. Research/optimization limits: docs/STEAM_PRICE_BATCHING.md;
proposed implementation: docs/STEAM_PRICE_BATCHING_PLAN.md. Implementation has not
started. Deferred UI requests are recorded in docs/ROADMAP.md. No publication is authorized.

## Publication and version

Version 0.5.0-beta is defined in steam_price_polisher/version.py and shown in
startup, /api/health, and the page. Follow README versioning: 0.MINOR.PATCH-beta,
minor for substantial features, patch for refinements; first stable release 1.0.0.
Public display name: Steam Currency Comparer. Keep package, script, environment,
cache, and legacy API names compatible. Source repository:
https://github.com/instant-results/steam-currency-comparer.
The user authorized coherent commits and a local merge into main. No push, tag,
release, or public deployment is authorized.
README images retain their historical 2026-09-23 example capture.

## Product behavior

- Three visible keyboard-accessible tabs: Your wishlist, Developers, Publishers.
  Owned library is hidden behind the server's internal OWNED_LIBRARY_ENABLED=False
  flag. Its tab/form stay hidden, library.js exits before touching storage/requests,
  and /api/library-jobs returns 404 without creating jobs. A saved library active
  tab falls back to wishlist; navigation skips the hidden button. Saved library
  data is preserved and cannot change currencies or lock the visible controls.
  Explicit internal QA can opt in with WebApplication(owned_library_enabled=True);
  then library appears directly to the right of wishlist. A key alone does not
  enable it. Leave the default off until the roadmap's live checklist passes.
- Shared sidebar: PL/PLN, US/USD, DE/EUR, NO/NOK, GB/GBP; any baseline and one or
  two alternatives. Default PLN against USD/EUR. Temporary baseline conflicts
  preserve remembered comparison choices until explicit checkbox edits replace them.
- Wishlist supports Your Rank, Date Added, Name; Name prefetch learns missing
  titles and reuses baseline prices. Numeric wishlist profiles need no key.
- When enabled internally, Owned library requires server-side STEAM_WEB_API_KEY for numeric profiles too.
  Supports SteamID64 and community profiles/id URLs; no keys/cookies in browser
  requests. GetOwnedGames on the public API host returns visible games in one
  request, includes names, and excludes free-to-play games. Name is default;
  Steam order preserves API order, not purchase dates/playtime/wishlist rank.
  Responses must match game_count; deduplicate IDs and reject >1,000 distinct
  games without silently truncating. Explicit empty libraries complete without
  rates/prices; missing/rejected keys, private/unavailable libraries, TLS,
  local network denial, malformed responses, and other failures have clear messages.
  Returned games are not a complete license/DLC inventory. Prices are current
  storefront offers, not purchase prices. See docs/STEAM_OWNED_LIBRARY_API.md.
- Wishlist/the internal library share comparisonRow, CSS table columns, artwork, both compact
  credits, sale prices, absolute/percentage differences, filters, search, sorting,
  unavailable toggle, retry, cancellation, and CSV. Keep column alignment and
  typography consistent. Credits show all names; unavailable/pending labels are
  explicit. Shared fluid grids align name lists and contain long-name wrapping.
  See docs/TEXT_AND_LOCALIZATION.md when editing wording or typography.
- Internally enabled library results, filters, sorting, currencies, request/profile, and access token
  live independently in polisher-library-job session storage. Completed library
  results outlive server jobs. Active jobs reconnect; expiry preserves checked
  rows and clears credentials. Active restored library restores its currencies.
  Existing results retain their own currencies until a new comparison. Retry
  uses the saved run's settings; submitting again uses current sidebar choices.
- Any running comparison locks shared currencies and other tabs' starts. Search
  on catalog tabs remains available. Return to the owning tab to cancel. Unopened
  catalogs wait for wishlist/library/other-role work to finish before auto-start.
- Developer defaults: Supergiant Games, CD PROJEKT RED, Techland, three games each.
  Publisher defaults: Devolver Digital, THQ Nordic, 11 bit studios, independent
  curation. See docs/FEATURED_CATALOGS.md. Search/add/Load more uses exact names
  in the requested role. Paid DLC/soundtracks are included; free products are
  hidden after checking. Missing prices alone do not mean free.
- Catalog roles preserve independent selections, results, searches, positions,
  rates, access tokens, and compact/column credit modes (20 catalogs per role).
  Defaults replace retired featured entries while keeping user selections.
  Legacy creator state migrates only explicit matching roles; homepage selections
  are discarded. Legacy Creator classes/routes remain compatible; no Creator UI.
- Catalog statistics use unrounded differences, equal product weights, mean,
  median, sample/coverage counts; exclude missing/pending/free/zero-reference values.
  One visible heading aligns role tables; hidden headings support screen readers.
  Preserve credit-column mode, synchronized narrow scrolling, statistics slots,
  baseline divider, and Load more arrow styling.
- Prices retain each storefront's final/base/discount independently. Discount
  mismatches get badges/filter. Product-wide differences use cheapest converted
  alternative; percentage is undefined against zero. Tooltips show provenance.
- The three visible tabs and internal library export CSV schema 1 with identical headers. Library adds
  library_profile and library_loading_order at the end, preserving existing
  columns' positions. source_tab includes library. Both profile attribution
  options default off and affect only their own columns. Credits, price/rate
  provenance, both conversion legs, failure details, and request counts remain.
  One row per observed storefront, one per uncompared item; catalog membership
  repeats products. Pending catalog products are omitted. Export adds no requests.

## Architecture and constraints

Python WSGI/SQLite; vanilla HTML/CSS/JavaScript, no build step.
- serve_web.py: loopback preview with exclusive listener, duplicate rejection,
  interrupt/termination/parent-exit cleanup. Verify listener and health before
  restarting; keep launching sessions alive. Existing port 8765 was occupied;
  this feature's live preview was started at 8766. Check versions before reuse.
- web_app.py: same-origin POST checks, capability-token private jobs, one paced
  worker, three starts per owner/minute, one active job per owner, one-hour expiry.
  POST /api/library-jobs is disabled by default; internal opt-in accepts only
  profile/regions/home/name-or-steam order;
  shared GET/cancel /api/jobs routes retain private authorization. Library jobs
  reuse AnalysisRunner, CachedPriceService, and exchange-rate conversion.
- creators.py: exact-role public registry, bounded discovery/cache, compatibility
  routes. Search verification rejects failed/stale role checks. Catalog pages
  advance through actual returned slots, including skipped packages/bundles;
  Steam may ignore count=12 and return 25. Never forward/execute upstream HTML.
- Cache schema 6: prices/free/credits; regular price TTL one hour, sales 15 minutes,
  rates 24 hours, catalogs six hours. Older missing sale/credit metadata refreshes
  once on comparison. Stale fallback is labeled and never masks local network denial.
- NBP quotes PLN per unit; A-to-B conversion rate[A]/rate[B], PLN=1; retain both
  dates/provenance. Germany is the EUR storefront proxy.
- Verified TLS, bounded retries, 1.5-second paced Steam requests. Live preview
  needs outbound access. Local permission denial is non-retryable and stops jobs.
- Structured diagnostic logs exclude profiles, keys, cookies, tokens, URLs,
  response bodies, raw exceptions, source lines, locals, and private file paths.
  Local data/log rotation remains ignored under .steam-price-polisher/.

## Verification and open work

141 Python tests and 63 frontend tests pass, plus JS syntax and diff checks.
Library coverage includes retrieval, parsing, empty/private/missing/rejected key
responses, validation, origin/tokens, cancellation, cross-tab locking, caching,
Name/Steam order, independent filters/sorting, reload, expiry, shared CSV headers,
profile opt-in, accessible references, unique IDs, and opt-in four-tab navigation.
Deferral checks cover default-disabled job starts and hidden markup, three-tab
keyboard navigation, fallback from a saved library tab, dormant saved jobs,
unchanged saved state/currencies, and unlocked visible comparison controls.
Real browser sample-price QA verified filters/search/reload and CSV download:
all three loaded products export despite an active filter, with no profile values.
Desktop and 390 CSS-pixel checks show aligned header/cell boundaries, aligned
credit-name starts, long-name wrapping, bounded page width, and no console errors.
QA fixture/scripts/screenshots stay ignored under .steam-price-polisher/qa/library.

The user-supplied live profile is absent from tracked code/docs/tests. Anonymous
live probes returned HTTP 401 for keyless GetOwnedGames and sign-in redirects
for games HTML/XML. The actual library UI reported the missing-key setup message
and released controls correctly. Successful authenticated retrieval of that
profile remains blocked by the absent local Steam API key; do not claim live
success. Sample-price fixtures are explicitly separate from real ownership data.

Owned-library code is retained, but the stage is deferred rather than complete.
TODO: complete key registration/Steam Guard, run authenticated live retrieval and
comparison checks with the previously supplied profile outside tracked fixtures,
verify restoration/export/diagnostics/locking, then decide on default visibility.
See docs/ROADMAP.md for acceptance criteria. Steam price retrieval batching is
the selected next backend stage; UI improvements remain deferred.
Research validated 25-item StoreBrowse and appdetails batches across PL/US/DE/NO/GB.
Recommend StoreBrowse metadata plus per-country appdetails price batches; no usable
multi-country request found. StoreBrowse best offers can choose bundles and use
different base/discount semantics, so they are not a drop-in price replacement.
Retrieval should accept more storefronts independently of current UI/API limits.
Default plan: configurable 100-item batches, URL budgets, completeness checks,
and bounded recovery; use the same hybrid pipeline even for one game. There is
no single-game optimization path. The discount metric is current versus regular
base price of the same offer; Steam-selected offers will be shown separately via a checkbox.
See docs/STEAM_PRICE_BATCHING.md and docs/STEAM_PRICE_BATCHING_PLAN.md for details.
Sorted wishlist API remains research only. A local developer/publisher directory
is deferred at the user's request; no crawler or persistent company index exists.

## Git state

Working branch: codex/steam-price-batching, created from main on 2026-10-18.
Planning documents were committed as afe782c. Subsequent batching research and
handoff/roadmap updates are committed before the approved implementation; no application code has changed yet.
codex/owned-library-tab is merged locally into main with separate
feature, test, and documentation commits; the feature branch is retained.
The hidden prototype and live-testing TODO are included in the merge. No push,
tag, release, or deployment has been performed or authorized. Keep feature/test
changes separate when committing future work. Runtime/cache data, local wishlists,
QA scripts/fixtures/screenshots, downloaded files, secrets, and populated
configuration files remain outside Git.
