# Development roadmap

Updated: 2026-10-18. Completed work is marked below; remaining targets are planned.
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

Possible later tuning: a smaller first window to improve first-result latency,
opt-in retrieval instead of always retaining best offers, and authoritative regular
bundle/package price enrichment. These require their own product/performance checks.
Third-party providers and new countries remain unselected future investigations.

## TODO: deferred comparison experience improvements

These requests are recorded for later work and are outside the backend branch.

### Load the example automatically

- On a fresh visit, load the seven-game example automatically. Restore an existing
  comparison first when available, without overwriting a user's loaded wishlist.
- Consider removing the redundant "Try an example comparison" button and update
  empty-state wording. Coordinate automatic work with existing cross-tab jobs.

### Change currencies without reloading the game list

- Allow baseline and comparison selections to update an already loaded list,
  preserving games, search, filters, sort choices, and catalog positions.
- Retain observations independently of the baseline, including partial regional
  results. Recalculate immediately when the needed prices are available; fetch
  only missing/stale data when necessary, with clear progress and provenance.
- Evaluate preloading all five storefronts after backend batching is measured;
  prioritize selected storefronts and avoid making large lists wait unnecessarily.
- Consider fetching the latest NBP Table A in one request and retaining the four
  supported foreign rates plus PLN identity. Preserve publication/retrieval dates,
  cache rules, and cross-rate calculation through PLN.
- Keep statistics, discount badges, availability, saved state, and CSV exports
  consistent with the active currency selection across visible tabs.

### Align the loading-order dropdown

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
