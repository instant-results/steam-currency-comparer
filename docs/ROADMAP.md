# Development roadmap

Updated: 2026-10-14. Completed work is marked below; remaining targets are planned.
See [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) for the current application state
and [USAGE.md](USAGE.md) for implemented behavior.

The developer/publisher feature branch and the export/wishlist-credit stage are
complete. Owned-library code is retained in 0.5.0-beta, hidden behind an internal
flag while authenticated live testing is deferred.

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
