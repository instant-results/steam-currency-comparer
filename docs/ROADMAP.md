# Development roadmap

Updated: 2026-10-13. Completed work is marked below; remaining targets are planned.
See [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) for the current application state
and [USAGE.md](USAGE.md) for implemented behavior.

The developer/publisher feature branch and the export/wishlist-credit stage are
complete. The next stage is the user's owned library.

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

## Next stage: the user's owned library

- Add an Owned library tab alongside Your wishlist, Developers, and Publishers
  to compare the games the user owns on Steam.
- Research and verify Steam's owned-library retrieval before implementation,
  including required credentials, visibility/privacy constraints, and pagination.
  Document the supported input and clear handling of private or unavailable libraries.
- Reuse storefront choices, price/rate caching, comparison arithmetic, and the
  unified CSV format; keep library results/state separate and honor shared job locking.
- Define ownership-specific product handling during that stage, with tests for
  successful retrieval, empty/unavailable libraries, and restoration of tab state.

## Deferred research

A local searchable developer/publisher directory with aliases and ranking remains
a potential TODO. Its sources, refresh policy, and catalog ingestion need planning;
no crawler or persistent company index is part of the immediate next stages.
