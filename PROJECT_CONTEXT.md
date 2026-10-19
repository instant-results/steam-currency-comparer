# Steam Currency Comparer — development handoff

Updated: 2026-10-20. Current state, not a change log.

## Start here

Read README.md and docs/USAGE.md, then inspect code and Git status.
Integration target: `main`. Version: **0.6.2-beta** in
steam_price_polisher/version.py. Current branch: `main`.
Substantial features increment MINOR; refinements increment PATCH; first stable
version is 1.0.0. Automatic example loading and shared frontend coordination are
integrated into main from `codex/automatic-example-loading`. Feature/documentation
and regression tests are committed separately. No feature work remains in this
scope. Main, including the merge, has been pushed to GitHub. Tags, releases and
deployment have not been requested. For future features, push the branch,
open/review/test a pull request, merge it on
GitHub, synchronize main, then delete the confirmed merged branch remotely/locally.
Repository: https://github.com/instant-results/steam-currency-comparer.

Steam batching, separate best offers, whole-percent calculated discounts and origin
tooltips are complete on main. Keep future feature and added test changes in
separate coherent commits. Do not commit local QA, caches, profile identifiers,
wishlists, secrets or runtime data. Dynamic currencies during/after loading and
loading-order dropdown improvements remain deferred; see docs/ROADMAP.md.

## Current product behavior

- Fresh visits automatically compare the seven-game example, with no example
  button. Restore saved wishlist jobs first, including expired-job retry context.
  Typing a profile dismisses a queued example; failures/cancellation require retry.
  Examples wait until the wishlist is visible and the shared coordinator is idle.
- Three visible tabs: Your wishlist, Developers, Publishers. Owned library remains
  hidden/disabled behind OWNED_LIBRARY_ENABLED=False pending authenticated live
  API-key QA. A key alone does not enable it. Its saved state remains dormant and
  must not lock controls or restore currencies while disabled.
- Five supported pairs: PL/PLN, US/USD, DE/EUR, NO/NOK, GB/GBP. Default PLN against
  USD/EUR. Public validation still requires one baseline and one or two alternatives.
  Remember temporarily conflicting choices; active jobs lock shared currency controls.
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
Branch preview: http://127.0.0.1:8766/, health confirmed 0.6.2-beta, with outbound
access for live QA. The earlier preview on 8765 still reports 0.6.1-beta. Keep the
branch preview's launching session alive; check health again before relying on it.

web_app.py retains same-origin POST checks, capability-token job access, one paced
worker, one active job per owner, three starts per minute and one-hour job expiry.
Wishlist/example/catalog/internal library jobs now use CachedBatchPriceService and
SteamBatchProvider in batching.py. CLI's existing provider remains compatible;
web jobs have no special single-game retrieval path.

BatchPolicy defaults: metadata/price sizes 100, encoded URL budget 6,000 bytes,
7 logical recovery calls and 21 physical attempts per planned batch, shared across
children. Configurable via JobManager(batch_policy=...). One country per request.
Default price batches use appdetails filters=price_overview. StoreBrowse requests
basic info and best_purchase_option. Both datasets require two requests per country
per window cold. Retrieval fixtures exercise more than three/five countries; new real
countries still require validation before enabling them in configuration/UI.

Match IDs, not array positions. Validate currencies, prices, metadata, missing and
duplicate records. Successful empty appdetails arrays mean no price, not free.
Only incomplete/malformed/400/414 batches split. 429/transient/TLS/denial do not fan
out. Retry-After defers later work even after final failure; pacing waits are cancellable.
Normal Steam pacing remains 1.5 seconds. Local permission denial stops jobs.

Cache schema 8 tracks calculated discounts and retains country-context English metadata (24 h) and best offers (15 min).
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
Diagnostic logs exclude profiles, credentials, URLs, bodies, raw exception text,
source lines, locals and private paths. Aggregate batch logs are privacy-filtered.

## Verification and measurement

Merge verification: all 165 Python tests and 84 frontend tests pass;
JavaScript syntax and Git diff checks pass. New coverage exercises fresh startup,
restoration/expiry, hidden catalog reconnect, initialization races, user priority,
cancellation/retry, unavailable storage and enabled/disabled library coordination.
Live browser QA confirms seven example results load automatically, survive reload
and remain intact after catalog work; shared controls lock during catalog startup.
The button is removed and the form remains aligned at desktop/medium widths.
Screenshot: ignored .steam-price-polisher/qa/automatic-example.png.
Additional live profile QA covered the full wishlist, reload during/after loading,
cancellation/partial restoration/retry, catalog waiting and refresh, display
controls and CSV. No functional defects or browser console warnings/errors found.
Detailed report: ignored .steam-price-polisher/qa/public-wishlist-behavior.md;
profile-linked screenshots, snapshots and exports remain local and uncommitted.
Tests cover batching limits/recovery/cache/cancellation, five/six storefronts, offer
semantics, shared physical-attempt accounting, rate-limit backoff, all existing job
contracts, checkbox rendering without requests, credit columns and CSV separation.
Earlier batching browser QA used labeled isolated fixture prices to confirm both
offers, aligned columns and refresh persistence. QA artifacts remain ignored.

One live cold run per version with the supplied wishlist capped at the same 200 IDs,
PL vs US/DE, normal pacing. Before: 815.194 s, first row 4.897 s, 534 price attempts,
8 HTTP 429s, 157 comparisons, 2 technical failures. After: 20.664 s, first 100 rows
10.931 s, 6 appdetails + 6 StoreBrowse attempts, no errors, 158 comparisons. All 471
regional current/base price pairs shared by the 157 comparable games matched.
One wishlist and two NBP requests in each run. New best-offer comparisons: 158.
This measures HTTP-delivered backend results, not browser paint, and is not a
statistical speed guarantee. See docs/STEAM_PRICE_PERFORMANCE.md for full results.
Approved research TODOs: larger batches, smaller initial windows, and reduced delivery delay.
Third-party price providers and publishing default offers before best offers are
rejected. Early publication of complete fresh cached rows is a potential future TODO,
without expired-data background refresh; see docs/ROADMAP.md.

Owned-library successful authenticated live QA remains deferred until Steam Guard/
API-key setup. Do not claim the public wishlist benchmark validates owned-library
retrieval. Existing hidden prototype and local main merge remain as before this branch.
