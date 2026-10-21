# Steam Currency Comparer — development handoff

Updated: 2026-10-21. Current state, not a change log.

## Start here

Read README.md and docs/USAGE.md, then inspect code and Git status.
Current branch: `codex/sticky-regional-scrollbar`.
Version remains **0.7.0-beta** in
steam_price_polisher/version.py. NBP preparation, post-load currency switching and
37-currency comparisons are complete and integrated through
[PR #1](https://github.com/instant-results/steam-currency-comparer/pull/1), merge
`c9e283d`. Local and remote main were synchronized, and
`feature/post-load-currency-switching` was deleted locally and remotely after
verifying its published commits were present on remote main. No feature work
remains on that branch. No tag or GitHub release was created.

Use a new feature branch for subsequent feature work. Commit implementation/docs
and added regression tests separately, push before opening a PR, and verify the
GitHub merge before branch cleanup. Substantial features increment MINOR;
refinements increment PATCH; first stable version is 1.0.0.
Repository: https://github.com/instant-results/steam-currency-comparer.

Current frontend work adds a blue horizontal scrollbar above each comparison,
limited to the visible regional columns and sticky within its comparison section.
Currency-picker scrollbars use the same blue treatment. Default baseline/regional
amounts and sale details align vertically, with matching font metrics, including
narrow screens. Catalog synchronization remains; the redundant scrolling-arrow
buttons and caption have been removed. The separate
stationary-heading redesign has not been implemented. Frontend checks: 113 tests
passed; isolated browser QA at 1440px/390px verified scrollbar geometry, sticky
bounds, bidirectional synchronization and default-price alignment/typography.
Approved implementation/docs and earlier documentation closeout are committed as
`57e0861`; regression tests are committed separately as `57a384e`.
The subsequent scrolling-arrow removal is implemented on the same branch.

Steam batching, separate best offers, whole-percent calculated discounts and origin
tooltips are complete on main. Keep future feature and added test changes in
separate coherent commits. Do not commit local QA, caches, profile identifiers,
wishlists, secrets or runtime data. Currency switching is scoped to after loading:
fetch selected Steam storefronts initially, then fetch additional data on demand
without reloading the wishlist. Retain completed observations for immediate reuse.
Steam backend support is implemented and live-validated. Frontend currency switching
is implemented for wishlist/example, Developers and Publishers; see docs/ROADMAP.md. Mid-load switching and loading-order improvements remain deferred.

## Current product behavior

- Fresh visits automatically compare the seven-game example, with no example
  button. Restore saved wishlist jobs first, including expired-job retry context.
  Typing a profile dismisses a queued example; failures/cancellation require retry.
  Examples wait until the wishlist is visible and the shared coordinator is idle.
- Three visible tabs: Your wishlist, Developers, Publishers. Owned library remains
  hidden/disabled behind OWNED_LIBRARY_ENABLED=False pending authenticated live
  API-key QA. A key alone does not enable it. Its saved state remains dormant and
  must not lock controls or restore currencies while disabled.
- 37 live currencies, one representative storefront each (US for USD, Germany for
  EUR), any baseline and one to 36 alternatives. Default PLN against USD/EUR. Shared
  registry: steam_price_polisher/storefronts.json, escaped into HTML for the browser.
  Searchable bounded picker, Select all/Clear, retained conflicting preferences and
  shared busy locking. See docs/STOREFRONTS.md for mapping and live validation.
- The matrix pins game/title and baseline on the left and DIFFERENCE on the right.
  Regional headings/default/best-offer slots scroll together. Catalog tables share
  scroll positions, suppress delayed synchronized events and keep separate slots for
  missing offers. Narrow screens put identity above the pinned price edges. Large
  catalog statistics are expandable and their state survives rerender/reload.
- Wishlist: Your Rank, Date Added, Name; public numeric profiles need no key, vanity
  resolution optionally uses a server-side Steam key. At most 1,000 games, no silent
  truncation. The 200-game performance cap exists only in an ignored benchmark harness.
- Default offers retain appdetails semantics. A shared checkbox reveals separately
  labeled Steam best purchase options with package/bundle names and links. Both sets
  are always fetched, retained in results and exported; toggling needs no download.
  Default offers continue to drive filters, sorts, counts and catalog statistics.
  The checkbox survives tab refresh; older saved results need a new comparison.
- Anonymous best offers assume no existing ownership. Country offers can be different
  products. Subscription offers are unsupported. StoreBrowse omits explicit currency;
  best-offer currency is attributed to requested storefront context and labeled as such.
- Discounts prefer Steam's reported percentage when consistent with regular/current
  prices, allowing integer rounding/truncation and cent rounding. Only missing or
  inconsistent percentages use (regular-current)/regular × 100, floored to whole percentage points and marked ≈. Provenance is retained in cache/results/CSV and shown when hovering over discount badges.
  Never borrow game base prices for bundles or treat compliance recent-low fields as
  regular prices. Bundle/ambiguous regular discounts stay unknown; current prices work.
- Artwork, both credits, search, filters, sale badges, absolute/percentage differences,
  cancellation/retry and unavailable toggles remain. Maintain header/cell alignment and
  typography; see docs/TEXT_AND_LOCALIZATION.md. Best-offer differences use their own color.
- Catalogs preserve exact developer/publisher roles, defaults, search, Load more,
  independent saved state, optional credit columns, page cursors and grouped statistics.
  Free products are hidden only with sufficient evidence. Paid DLC/soundtracks remain.
  Default developers: Supergiant/CD PROJEKT RED/Techland. Publishers:
  Devolver Digital/THQ Nordic/11 bit studios. See docs/FEATURED_CATALOGS.md.
- CSV schema 1 keeps existing columns and appends best_offer_* columns. Profile
  attribution remains optional/off per wishlist/library source. All tabs share headers.
  Exports retain both offer sets regardless of checkbox, including partial best offers.
  Formula escaping, credits, original/base/final prices, rates and provenance remain.

## Architecture

Python WSGI/SQLite, vanilla JS/CSS, no build step. serve_web.py is a loopback preview
with exclusive listener and lifecycle cleanup. Check listener/health before restarting;
keep its launching session alive. Do not expose it publicly.
Frontend comparisonCoordinator in web/app.js owns job reservations, initialization
holds, shared busy state and keyed idle tasks. All tabs register/release their jobs;
catalog auto-loading has priority over the example and no longer polls busy flags.
Saved catalog jobs on hidden tabs initialize/reconnect before new automatic work.
Per-tab state still handles rendering/results; the backend worker is unchanged.
Check listeners and `/api/health` before relying on an existing preview; previous
8765/8766 processes may no longer be running. Currency-switching browser QA uses
an isolated fixture server and temporary cache, separate from live Steam/NBP QA.

web_app.py retains same-origin POST checks, capability-token job access, one paced
worker, one active job per owner, three starts per minute and one-hour job expiry.
Wishlist/example/catalog/internal library jobs now use CachedBatchPriceService and
SteamBatchProvider in batching.py. CLI's existing provider remains compatible;
web jobs have no special single-game retrieval path.

POST `/api/jobs/{id}/currencies` accepts home/regions with the source job's bearer
token after complete/partial completion. It creates a separately tokenized job on
the same worker, reusing the loaded game order and catalog membership/cursors;
discovery is not repeated. Original results stay intact for polling or retry after
failure/cancellation. Active jobs lock currency changes across their comparison
chain as well as retaining existing owner/capacity/start-rate limits.
Successful regional prices, metadata and best offers (including observations from
uncompared games) reuse the existing shared cache with independent freshness rules.
Only missing/expired selected-country data is retrieved. Selection/order remain
private expiring memory; no profile mappings enter SQLite.
Frontend **Update currencies** applies to the current tab after loading. Wishlist
source credentials/displayed snapshots stay separate from pending job credentials;
catalog updates submit the union of loaded IDs through product mode and preserve
local groups/order/expansion. Rows, headings, rates, statistics and CSV switch
together at complete/partial completion. Failures/cancellation preserve the old
snapshot; retry repeats the failed selection. Search/filter/sort/scroll and offer/
credit display settings survive. Reload restores displayed and pending state
separately; hidden catalog jobs reconnect before automatic work. Catalog cursors
retain discoveryHome: Load more uses zero when the displayed baseline differs,
then deduplicates against loaded products. Expired wishlist sources need a new
initial comparison; completed saved snapshots stay available. Owned library stays
disabled; additional regional USD groups and mid-load switching remain outside scope.

BatchPolicy defaults: metadata/price sizes 100, encoded URL budget 6,000 bytes,
7 logical recovery calls and 21 physical attempts per planned batch, shared across
children. Configurable via JobManager(batch_policy=...). One country per request.
Default price batches use appdetails filters=price_overview. StoreBrowse requests
basic info and best_purchase_option. Both datasets require two requests per country
per window cold. Retrieval fixtures cover all 37 countries; all configured
representatives were live-validated with public sample games on 2026-10-20.

Match IDs, not array positions. Validate currencies, prices, metadata, missing and
duplicate records. Successful empty appdetails arrays mean no price, not free.
Only incomplete/malformed/400/414 batches split. 429/transient/TLS/denial do not fan
out. Retry-After defers later work even after final failure; pacing waits are cancellable.
Normal Steam pacing remains 1.5 seconds. Local permission denial stops jobs.

Cache schema 9 adds NBP source/table-fetch metadata to schema 8's calculated discounts
and country-context English metadata (24 h) and best offers (15 min).
Default prices retain regular 1 h/sale 15 min/missing 1 h/unavailable 6 h. Existing
price/rate cache rows remain compatible. Enrichment does not reset price age. Known
empty credits do not refetch forever. Temporary failures may use labeled stale data.
Restricted metadata cannot erase known successful metadata. No profile-to-game mapping.

Rank/date jobs prepare bounded windows and emit ordered rows; Name prefetch learns
names and reuses observations. Physical Steam data attempts are charged once to the
first emitted row of a window, including prefetch on the first window. Cache-hit
counts describe observations. The legacy CSV live_price_requests includes metadata
and offer attempts; repeated regional CSV rows must not be summed naively.

NBP supplies PLN per unit. Cross-rate A→B is rate[A]/rate[B]; retain dates/provenance
for both legs, PLN=1. Germany is the EUR proxy. Rates stay cached 24 h.
NBP retrieves both complete tables A and B upfront for foreign-currency requests,
refreshing only missing or expired tables and caching all rates. Table failures are
independent: available requested rates remain usable when the other table fails. No Steam country is
enabled by adding NBP coverage. Each table is validated and cached atomically;
source, publication date and retrieval age survive reopen and stale fallback.
Successful tables survive failures of another required table. Local network denial
stops retrieval. Existing per-currency caches migrate without losing price data.
Diagnostic logs exclude profiles, credentials, URLs, bodies, raw exception text,
source lines, locals and private paths. Aggregate batch logs are privacy-filtered.

## Verification and measurement

0.7.0-beta integration: all 208 Python tests and 110 frontend tests passed, along
with JS syntax and diff checks. The merged tree matches the tested branch tree.
GitHub had no configured CI checks. Added coverage exercises all 37 baselines/full selections,
API/HTML registry consistency, Steam amount units, cached baseline swaps, missing
offer slots, 37-region CSV, restoration and delayed catalog scroll events. Browser
QA passed at 1440px and 390px with synthetic prices: all-currency baseline changes,
reload, optional credits, both offers, no page overflow, fixed pinned columns,
long VND values without cell overflow and catalog scroll synchronization. The
333-row downloaded CSV retained all 37 storefronts and both offer sets for nine
products. Browser console checks were clean. Check `/api/health` before reusing a
local preview; restart the server after Python code or version changes.

Live Steam/NBP backend validation passed on 2026-10-20 using an isolated temporary
cache and normal pacing/retries. The wishlist loaded once; a baseline swap and
switch back made zero HTTP requests, and adding GBP fetched only UK data. Both
NBP tables loaded once and previously unselected rates reused the cache. No HTTP
errors occurred. Additional public-game checks validated returned currencies and
NBP coverage for all 37 representative countries; this is not a full-list timing
benchmark. Aggregate QA reports and screenshots remain local and ignored.

The historical 0.6.0-beta batching benchmark compared one cold 200-game run per
version, PL vs US/DE: 815.194 seconds before and 20.664 seconds after. It measures
HTTP-delivered backend results, not browser paint or 37-country performance.
See docs/STEAM_PRICE_PERFORMANCE.md for the complete protocol and limitations.

## Remaining work

No further implementation task beyond the current scrollbar/alignment refinement
has been selected. See docs/ROADMAP.md for:

- Loading-order dropdown alignment.
- Loading performance research: larger batches, smaller initial windows and
  reduced delivery delay. Early publication of complete fresh cached rows remains
  a potential investigation, without expired-data background refresh.
- Deferred mid-load currency switching and additional regional USD groups.
- Authenticated owned-library QA before considering enablement.

Third-party price providers and publishing default offers before best offers
remain rejected approaches.

Owned-library successful authenticated live QA remains deferred until Steam Guard/
API-key setup. Do not claim the public wishlist benchmark validates owned-library
retrieval. The existing prototype remains hidden and disabled.
