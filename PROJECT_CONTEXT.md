# Steam Currency Comparer — development handoff

Updated: 2026-10-13. This is a current-state summary, not a change log.

## Start here

Read AGENTS.md and README.md, then inspect Git status and the implementation.
Follow the user's next request; do not invent new features or deploy the app.
Developer and publisher searches/catalogs are implemented as independent tabs
alongside Your wishlist. No Creator category appears in the UI. This feature
branch is complete. CSV unification is implemented on codex/unified-csv-exports;
the remaining targets are in docs/ROADMAP.md.

## Publication and version

Current version: `0.4.6-beta`, defined in `steam_price_polisher/version.py` and
shown in the header, startup log, and `/api/health`. Follow README.md versioning:
0.MINOR.PATCH-beta, minor for substantial features, patch for refinements.
The intended first stable release is 1.0.0. Version bumps do not publish the app.
The source repository is https://github.com/instant-results/steam-currency-comparer.
No new tag, push, release, or public deployment is authorized.
Public display name is Steam Currency Comparer; existing package, script,
environment-variable, API, and cache names retain compatibility.
README screenshots in docs/images show the 2026-09-23 seven-game example.

## Product behavior

- Your wishlist, Developers, and Publishers are separate keyboard-accessible tabs.
- Shared sidebar: PLN/Poland, USD/United States, EUR/Germany, NOK/Norway, GBP/UK;
  any baseline, one or two alternatives. Default PLN versus USD/EUR.
- Wishlist input has Your Rank, Date Added, and Name loading orders. Alphabetical
  prefetch learns missing names and reuses baseline prices. Rows append stably;
  table sorting resets to loading order. Search, filters, unavailable toggle,
  CSV export with optional profile attribution, retry, and cancellation remain.
  Wishlist comparisons now also require cached developer/publisher credits;
  older cache entries refresh once during comparison, without export-time requests.
- Developers starts with three games each from Supergiant Games, CD PROJEKT RED,
  and Techland. Publishers features Devolver Digital (US), THQ Nordic (Austria),
  and 11 bit studios (Poland), with examples made by different studios.
  Role defaults are curated independently; see docs/FEATURED_CATALOGS.md.
- Each role has a Show publisher column / Show developer column checkbox above
  search. Checked displays opposite-role credits in a separate labeled column;
  unchecked keeps compact credits beneath each title. The mode persists per tab.
  Steam appdetails credits share the price cache; old catalog entries/results
  refresh once to obtain missing credits.
- Each role has its own Find a developer/publisher form, results, selected names,
  pagination, rates, job token, and saved session state. Search verifies nonempty
  regional product catalogs for that role. Add & compare appends a catalog.
  No homepage catalog or third company role is offered.
- Load more uses exact-name developer/publisher product credits for both featured
  and searched names. Paid DLC/soundtracks count; free products are hidden after
  checking the free flag or zero baseline price. Missing prices alone do not mean free.
- Up to 20 catalogs per role persist in session storage under polisher-developer-job
  and polisher-publisher-job. Legacy polisher-creator-job migrates explicit role
  selections and their matching cursors; homepage catalogs are discarded rather
  than assigned a role. Legacy active tab creators maps to developer. Session state records featured IDs;
  changed defaults replace former featured entries and trigger a comparison of
  the new defaults, preserving user-added catalogs and their cursors.
- Shared currencies and comparison actions are locked while any comparison runs.
  Search is still allowed. An unopened role tab waits for the active job to finish;
  switch back to the owning tab to cancel it. Wishlist state remains independent.
- Existing comparisons retain their own currencies until Refresh comparisons.
  A baseline change resets pagination while preserving displayed products.
- Catalog statistics use equal product weight, unrounded percentage differences,
  mean, median, sample size, coverage, and cheaper/equal/pricier/uncompared counts.
  Missing, pending, free, and zero-reference products are excluded as appropriate.
- One visible heading aligns with all role tables; hidden headings support screen
  readers. Preserve table/header typography, column alignment, synchronized narrow
  scrolling, statistics slots, baseline divider, and the Load more arrow styling.
- Prices retain each region's final/base price and discount; mismatches get a badge
  and filter. Differences use the cheapest converted alternative. Zero reference
  makes percentages unavailable. Per-price provenance appears in hover tooltips.
- Results/rates persist in the browser tab; completed saved comparisons can outlive
  server jobs. Refresh explicitly requests new checks. All tabs export CSV schema 1
  with the same fixed columns, both credit lists, price/rate provenance, per-storefront
  differences, failure details, and cache/request counts. Wishlist attribution stays
  opt-in; catalog profile values and wishlist catalog fields are blank. CSV uses one
  row per observed storefront (one for uncompared products) and repeats products
  for each catalog membership. Pending products are omitted. See docs/USAGE.md.

## Architecture and constraints

Python WSGI and SQLite, vanilla HTML/CSS/JavaScript, no frontend build step.
- serve_web.py: exclusive loopback preview, default port 8765, duplicate rejection,
  interrupt/termination and parent-exit cleanup. Verify listener and health before
  reusing/restarting. Keep the launching session alive.
- web_app.py: same-origin validation, private bounded jobs, one paced worker.
  Three starts per owner/minute, one active job per owner, jobs expire after one hour.
- creators.py: legacy featured registry and role-specific public registry entries,
  exact-credit catalog parser/cache, anonymous name discovery. Internal Creator
  classes and old routes remain compatible; the frontend does not expose that role.
- GET /api/creators returns developers/publishers plus legacy creators.
  POST /api/creators/search takes query/home/role (developer or publisher), uses
  Steam SearchSuggestions internally to discover canonical names, and verifies
  only the requested role's product search. Legacy role-less requests remain supported.
- Search cache: 128 queries, ten minutes, keyed by term/region/role. Separate role
  verification page cache: six hours, 128 pages. Search rejects failed/stale checks.
- POST /api/creator-jobs retains featured/catalog/products modes and validated
  selectors. New tab initialization compares only that role's curated app IDs
  using products mode. Expansion uses the role selector. Existing result/cancel
  routes use private tokens. Legacy homepage jobs still supported internally.
- Steam search can ignore count=12 and return 25 entries; start=12 may repeat page
  zero. Parser bounds search pages to 50 rows and advances through returned slots,
  including skipped bundles/packages. No upstream HTML/scripts are forwarded.
- Price cache schema 6 includes free-product and developer/publisher credit metadata; regular prices refresh after
  one hour, known sale prices after 15 minutes, rates after 24 hours. Stale fallback
  is labeled. Catalog cache six hours, bounded and keyed by identity/region/cursor.
- NBP quotes PLN per currency unit. Convert A to B using rate[A]/rate[B], PLN=1;
  retain both dates and cache provenance. Germany is the EUR storefront proxy.
- HTTP/request policy modules handle verified TLS, retries, and pacing at 1.5 seconds.
  Local network denial is non-retryable, stops jobs, and never hides behind stale
  fallback. Run live previews with outbound access to Steam and NBP.
- Local diagnostics: data-dir/logs/events-PID.jsonl, 2 MiB rotation and three backups.
  Safe structured events exclude profiles, keys, cookies, and job tokens.
- See docs/USAGE.md for usage/methodology/lifecycle, DEPLOYMENT.md before hosting,
  docs/STEAM_CREATOR_SEARCH.md for catalog API evidence and compatibility limits.

## Verification and open work

Latest checks: 129 Python tests and 51 frontend tests, plus JS syntax/diff checks.
CSV checks cover identical headers across tabs and attribution settings, enriched
wishlist cache reuse, mixed provenance, both conversion legs, escaping/missing values,
zero references, overlapping catalog membership, and partial exports. This export
change was verified offline; no new live browser QA or network comparison was run.
New checks cover role-only search/cache keys, featured role registry selectors,
separate tab state/restoration, cross-tab worker locking, legacy migration, and
three-tab keyboard navigation. Live browser QA verified ConcernedApe developer and publisher searches/additions,
independent saved groups, restored legacy prices, and desktop/390px layouts with
no console errors. Preview port: 8765; verify the listener and /api/health version
before reuse. An already running process may serve an older release.
Live v0.4.4 QA verified compact/column modes, exact header/cell
alignment, saved tab preferences, and synchronized scrolling at 390px with no
console errors. Minimal DOM tests require complementary browser QA.

Next targets (planned, not implemented; see [docs/ROADMAP.md](docs/ROADMAP.md)):

1. Add compact developer/publisher descriptions beneath wishlist game icons/titles,
   reusing appdetails credits and price caching while preserving table alignment.
2. In the following stage, add a separate tab for the user's owned Steam library;
   verify retrieval, credentials, and privacy constraints before implementation.

The sorted wishlist API remains research only; see docs/STEAM_SORTED_WISHLIST_API.md.
Potential TODO: a local searchable developer/publisher directory with aliases,
ranking, and source/refresh planning. Deferred at the user's request; no crawler
or persistent company index is included.

## Git state

Working branch: codex/unified-csv-exports, created from main for CSV unification.
The implementation, tests, and documentation for v0.4.6 are versioned in separate
coherent commits, as authorized by the user. No push is authorized.
main is the repository's primary branch; there is no master branch.
The completed codex/developer-publisher-catalogs branch is merged locally into
main with a merge commit. Implementation, test, and documentation commits remain
separate in history, including the v0.4.5 version/roadmap handoff. The completed
catalog feature branch is retained. The local merge and CSV branch have not been
pushed; no push, tag, release, or deployment is authorized. Follow the user's next request before implementing
the planned roadmap. Keep runtime data, caches, screenshots, local wishlist
files, secrets, and populated environment files out of Git.
