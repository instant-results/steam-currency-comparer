# Development roadmap

Updated: 2026-10-22. These are development directions, without delivery dates or
release commitments. See the [README](../README.md) for current features, the
[usage guide](USAGE.md) for behavior and limitations, and the
[changelog](../CHANGELOG.md) for completed changes.

## Planned improvements

### Game titles and artwork

Improve the readability of long titles beside game artwork without squeezing the
price columns. Evaluate thumbnail size, identity-column width and arrangements
that adapt to the available space. No replacement layout has been selected.

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
