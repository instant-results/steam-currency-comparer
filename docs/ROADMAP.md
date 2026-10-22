# Development roadmap

Updated: 2026-10-22. These are development directions, without delivery dates or
release commitments. See the [README](../README.md) for current features, the
[usage guide](USAGE.md) for behavior and limitations, and the
[changelog](../CHANGELOG.md) for completed changes.

## Completed in 0.7.3

Baseline and comparison currency cards now include circular flags, with the EU
flag for EUR and Germany retained as its representative storefront. The artwork
loads from one bundled SVG sprite. Named currency summaries use commas and a
final conjunction, with the existing count summary for more than four alternatives.

## Completed in 0.7.2

Currency setup now sits above the full-width results, with draft discard on hide.
Wishlist search occupies the second header row. Filters and display choices share
a wrapping toolbar, with persistent, anchored best-offer help. Completion status
matches the checked-game count. Retry sits beside Compare regional prices, and
sorting headers cycle ascending, descending and original loading order with
compact directional indicators. Sticky storefront borders and spare desktop
identity width are aligned with the price columns. See the changelog for details.

## Planned improvements

### Game titles and artwork

The currency panel now sits above the comparison and collapses during loading,
freeing width for game identity. Desktop titles use a wider, adaptive column;
narrow layouts retain identity above prices. Evaluate further thumbnail and
title refinements against this layout without squeezing the price columns.

### Interface clarity

Review the remaining decorative arrows and distinguish them from useful link,
sorting and dropdown indicators. Keep labels, keyboard behavior and narrow-screen
layouts consistent across the comparison tabs.

### Loading performance

Investigate ways to show useful results sooner while keeping total loading time,
request volume and failure recovery under control:

- Compare batch sizes and smaller initial processing windows.
- Reduce the delay between results becoming ready and reaching the browser.
- Explore earlier display of complete, fresh cached rows while preserving order.

Keep default prices and best offers together in each published row. Preserve
request pacing, cache freshness, cancellation and result provenance. The
[existing measurement](STEAM_PRICE_PERFORMANCE.md) explains the baseline and its
limits; it does not guarantee the same performance for every list or storefront.

## Deferred stage: the user's owned library

The prototype is hidden and disabled during normal use. Successful authenticated
live validation is still required before considering it available. A configured
API key alone does not enable it.

Validation must cover:

- Authenticated retrieval, supported profile inputs and library-count limits.
- Public, private, unavailable and empty-library responses, plus rejected keys.
- Regional prices, credits, cancellation, retry and shared comparison locking.
- Saved-state restoration, filters, sorting, CSV attribution and narrow layouts.
- Exclusion of credentials and ownership mappings from logs and shared caches.

See [owned-library behavior](USAGE.md#owned-library) and
[retrieval research](STEAM_OWNED_LIBRARY_API.md) for its scope and limitations.
Automated fixtures complement, but do not replace, authenticated live validation.

## Longer-term exploration

- Currency changes during loading.
- Additional Steam regional USD pricing groups.
- Optional best-offer retrieval and verified regular prices for packages/bundles.
- A searchable developer/publisher directory with aliases and predictable ranking.

These ideas need further scope and feasibility work. They are not available
features or selected implementations.
