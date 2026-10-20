# Development roadmap

Updated: 2026-10-20. Completed work is marked below; remaining targets are planned.
See [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) for the current application state
and [USAGE.md](USAGE.md) for implemented behavior.

The developer/publisher feature branch and the export/wishlist-credit stage are
complete. Owned-library code is retained in 0.5.0-beta, hidden behind an internal
flag while authenticated live testing is deferred.

## Completed implementation: Steam price batching and separate offers

Branch: `codex/steam-price-batching`, version `0.6.0-beta`.

- Implemented appdetails price batches and StoreBrowse metadata/best-offer batches,
  per country, using one pipeline for all list sizes. Default 100 items, encoded
  URL limits, completeness validation, bounded recovery and shared pacing remain.
- Implemented independent cache ages, ordered progress, cancellation and request
  accounting. Retrieval accepts more than three storefronts; the current UI/API
  selection limit remains unchanged.
- Added the user-approved checkbox showing Steam-selected purchase options beside
  default game prices. Bundles/packages retain their identities; discounts never
  use a different product's base price or a compliance-only reference price.
- Completed one fresh-cache 200-game run per version. Results and limitations:
  [performance report](STEAM_PRICE_PERFORMANCE.md). No concurrency was introduced.
- Research and observed optimization ceiling: [investigation](STEAM_PRICE_BATCHING.md).
  Implemented architecture and acceptance checks: [plan](STEAM_PRICE_BATCHING_PLAN.md).

## TODO: loading performance research

Decisions recorded on 2026-10-20; these are research tasks, not implemented changes.

- **Larger batches:** test 120 and other candidate sizes against the 100-item
  default. Measure first-result and total latency, request counts, encoded URL
  and response sizes, completeness, retries and errors. Include list lengths near
  batch boundaries and more than three storefronts. A 200-game list still needs
  two windows at either 100 or 120; acceptance alone does not establish a speedup.
- **Smaller first window:** investigate a small initial batch followed by larger
  batches. Measure the first visible results against total loading time and added
  requests under unchanged pacing. Keep each published row complete for both offer
  types; do not introduce later best-offer enrichment.
- **Delivery delay:** investigate reducing the current 1.2-second polling delay.
  Compare simpler polling adjustments with push/long-poll approaches before choosing
  an implementation. Measure actual delivery latency and server/request overhead;
  preserve cancellation, reconnect behavior and access controls.

### Dropped approaches

- Third-party price providers: rejected; keep price retrieval with Valve.
- Publishing default offers first and attaching best offers later: rejected due
  to added state/update complexity. Preserve complete rows with both offer datasets.

### Potential TODO: publish complete fresh cached rows earlier

Fresh cached observations are already reused without fetching those prices again.
Publishing complete, fresh cached rows earlier would not inherently require later
replacement or value comparison. Showing expired data and refreshing it in the
background would require replacement handling; that is a different proposal.
Investigate whether complete fresh cached rows can be published earlier without
refreshing or replacing them during the same comparison. Exclude expired-data
background refresh from this potential task. The design must account for independently expiring metadata,
prices, best offers and exchange rates, plus requested row order. No cache-first
publication implementation has been approved; this is a potential future TODO.

Other unselected investigations: new countries, opt-in best-offer retrieval and
regular bundle/package price enrichment. Concurrency remains unselected.

## Comparison experience improvements

Automatic examples are complete on main; the remaining requests are recorded
for later work.

### Completed: load the example automatically

Completed in `0.6.2-beta` and merged from `codex/automatic-example-loading` into main.

- Fresh visits load the seven-game example automatically; the redundant button
  is removed. Existing wishlist jobs restore first, including expired-job retry
  context. Typing a profile dismisses a queued example.
- A shared frontend coordinator reserves job starts and schedules automatic work
  when idle. Saved catalog work reconnects even on hidden tabs. Examples wait
  until the wishlist is visible; active catalog work takes priority.
- Failures and cancellations retain the existing explicit retry behavior.

### In progress: change currencies after loading without reloading the game list

Branch: `feature/post-load-currency-switching`. Scope narrowed on 2026-10-20.

- Enable currency changes after loading finishes; changes during loading remain
  deferred. Preserve games, search, filters, sorting and catalog positions.
- Keep initial Steam retrieval limited to the selected storefronts. Reuse retained
  observations immediately when possible. When another storefront is selected,
  fetch its missing/stale data without retrieving the wishlist again. Keep both
  default and best offers. Further selection changes wait for that fetch to finish.
- Keep completed observations in the shared cache; switching back reuses fresh data.
  Currency-change jobs apply normal cache freshness rules. Show progress and preserve the old
  comparison while additional data loads, without relabeling old regional prices.
- Retain observations independently of the baseline, including partial regional
  results and failures. Keep statistics, discount badges, availability, saved state,
  and CSV consistent with the active selection.
- Separate supported storefronts from the set fetched for a comparison. Additional
  Steam countries require validation; worldwide preloading is not the default.

Current backend stage: NBP preparation and Steam currency-change jobs are implemented on the feature branch.
Complete tables A and B are fetched upfront for foreign-currency comparisons;
fresh tables are reused independently for 24 hours. All rates are cached, including
unselected currencies. A failed table does not block available requested rates.
Atomic cache schema 9
preserves table-specific publication dates, sources and retrieval ages. Fresh tables
and rates are reused, stale fallback remains labeled, and local network denial stops
retrieval. The current UI and public storefront validation still support five pairs.
The backend retains each job's loaded selection/order and catalog membership in
expiring memory. POST `/api/jobs/{id}/currencies` queues a separate comparison of
that selection after complete/partial completion, without repeating discovery.
The existing cache retains successful regional observations even for uncompared
games; default prices, metadata and best offers keep independent freshness rules.
Only missing/expired selected-country observations need Steam retrieval. Original
results stay accessible, including after failure/cancellation of the new job.
Token access, shared worker limits and a lock across related jobs apply.
Frontend integration (including combining loaded catalog pages, display state,
saved state and CSV selection) remains pending. No additional countries or
mid-load switching are included in this stage.

#### Next stage: frontend integration

The existing backend contracts are sufficient for the agreed five-storefront UI.
No additional backend feature is planned before wiring the frontend. The remaining
work is in `web/app.js`, `web/creators.js`, shared rendering/state, and frontend tests:

- Keep completed wishlist/example job IDs and tokens separately from a pending
  currency-change job. Submit home/regions to `/api/jobs/{id}/currencies`; do not
  call the initial `start()` path, which clears results, search and sort settings.
- Use `comparisonCoordinator` to reserve work before submission and lock shared
  currency controls until it finishes. Preserve per-tab results, filters, sorting,
  scroll position and the best-offer visibility setting. Do not switch mid-load.
- Keep displayed currencies, rates and rows together as one completed snapshot.
  Show progress separately while polling the new job; replace the snapshot together
  at complete/partial completion. Recompute statistics, badges and CSV from the new
  snapshot. On failure/cancellation keep the old snapshot and retry from its job.
- Catalog panes currently discard finished job tokens and combine several jobs in
  their local groups. For the full loaded selection, deduplicate loaded product IDs
  and submit one `/api/creator-jobs` request with `mode: "products"`, home, regions
  and app_ids. This existing path avoids discovery and reuses both offer caches.
  Keep group membership, display order, expansion and page state in the browser;
  do not run the current destructive `refreshFeatured()` reset during a switch.
- Preserve loaded catalog positions during switching. Page offsets belong to their
  discovery storefront: retain that context, and when Load more later uses a different
  storefront, restart discovery from its first page and deduplicate against loaded
  products. Never silently apply an old storefront's offset to a new one.
- Save the displayed snapshot and pending job credentials separately for reload,
  reconnect and tab changes. Handle 429 without discarding results. For expired
  wishlist jobs, explain that a new initial comparison is required; catalog product
  jobs can use the locally retained IDs. Keep the owned-library feature disabled.
- Cover successful cached/new-country switches, partial results, failed submission,
  cancellation, retry, expiry, reload and cross-tab locking in frontend tests.
  Verify desktop/narrow layouts, header/cell alignment, both offer sets and CSV in
  browser QA. Cached backend recomputation is still asynchronous (about eight seconds
  for the live 758-game check), so progress must not assume an instant response.

Additional countries, mid-load changes and the loading-order dropdown adjustment
remain separate work. Retain the current version until a version change is requested.

### TODO: align the loading-order dropdown

- Align the "Loading order" label and selected value's left text edges, verify
  vertical centering, and inset the down arrow consistently from the right border.
- Retain native keyboard/accessibility behavior and verify desktop/narrow layouts,
  including shared control styling and header/row typographic alignment.

## Completed stage: consistent exports and wishlist credits

### Unify CSV formats between tabs

Completed in `0.4.6-beta` on `codex/unified-csv-exports`. All three tabs use
CSV schema 1, with regression coverage for headers, credits, missing values,
attribution, currencies, and overlapping catalog membership.

- Define one consistent CSV schema for Your wishlist, Developers, and Publishers:
  column names and order, number/date formats, credit formatting, and missing values.
- Include developer and publisher credits in every tab's export, independent of
  display settings. Keep original/base/final prices, discounts, converted prices,
  differences, baseline currency, and exchange-rate/provenance fields consistent.
- Represent source-specific fields consistently: catalog role/name for catalog
  exports and opt-in wishlist attribution, with empty values where inapplicable.
  Preserve catalog membership when one product belongs to multiple selected catalogs.
- Retain UTF-8 spreadsheet compatibility, formula escaping, credential exclusion,
  and the current rule that running comparisons export only checked results.
- Reuse the shared `buildPriceCsv` serializer with fixed columns for every tab.

Done when all three tabs use the agreed schema and regression checks cover their
headers, credits, missing values, attribution, and comparison currencies.

### Add compact developer/publisher descriptions to wishlist rows

Completed in `0.4.7-beta` on `codex/unified-csv-exports`. Wishlist rows show
both credit lists using the catalog text styling. Regression checks and desktop/
390px browser QA cover multiple/missing names, stable rows, and table alignment.

- Show developer and publisher credit labels beneath each game's icon/title in
  Your wishlist, using the small, unobtrusive presentation from the catalog tabs.
- Reuse Steam appdetails credits and the existing price cache; show all reported
  names, including multiple developers/publishers, and handle missing credits.
- Preserve title/artwork layout, table alignment, loading order, filters, sorting,
  and narrow-screen behavior. Include the same credits in the unified CSV.

Done when wishlist rows show both credits with the existing compact styling,
including the built-in example and restored comparisons, without disturbing
price columns or issuing requests merely to change the display.

## Deferred stage: the user's owned library

Code and automated fixtures are implemented in 0.5.0-beta, merged locally from
codex/owned-library-tab. This stage is **not complete**: successful authenticated
live retrieval remains TODO. Steam Guard access/key registration is deferred at
the user's request. The tab and profile form are hidden by default; library
initialization/reconnection and /api/library-jobs are disabled too. Existing
library session data is preserved but cannot affect the visible comparisons.
Your wishlist, Developers, and Publishers remain available.

When internally enabled, Owned library appears immediately after Your wishlist
and shares its row renderer, table styling, credits, filters, sorting, exports,
unavailable handling, and cancellation/retry. State stays separate; prices,
rates, pacing, and job locking are shared. See [research](STEAM_OWNED_LIBRARY_API.md)
and [internal QA behavior](USAGE.md#owned-library). Automated coverage and sample
browser checks do not establish successful live ownership retrieval.

### TODO: authenticated API-key and library testing

- Complete Steam Guard/key registration locally. Keep the key out of chat, Git,
  browser requests, fixtures, screenshots, and diagnostics.
- Use an isolated QA WebApplication with owned_library_enabled=True; the normal
  launcher stays disabled. Test the previously supplied profile without adding
  its ID or ownership list to tracked files.
- Verify valid-key retrieval, numeric/community/custom-profile inputs, returned
  game count/selection, Name/Steam order, and documented coverage/limits.
- Verify real regional prices and rates, sale/credit metadata, cancellation,
  retry/cache reuse, and shared locking with wishlist/catalog comparisons.
- Check reload restoration, filters/sorts, CSV profile opt-in, safe diagnostics,
  and desktop/narrow layouts. Verify unavailable/empty or rejected-key handling
  where suitable test cases are available; automated cases remain complementary.
- Record authenticated live evidence and resolve failures. Only then decide to
  enable OWNED_LIBRARY_ENABLED by default and update README/usage/context.

Until that checklist passes, keep the owned-library stage deferred and avoid
presenting its UI or describing it as an available, fully verified feature.

## Deferred research

A local searchable developer/publisher directory with aliases and ranking remains
a potential TODO. Its sources, refresh policy, and catalog ingestion need planning;
no crawler or persistent company index is part of the immediate next stages.
