# Changelog

## Unreleased

- Developer and publisher tab with featured creators, icons, and regional price
  comparisons for three selected games per creator.
- Expandable Steam catalogs, shared price caching, cancellation, refresh of
  displayed products, and separate saved results for each tab. Creator search
  is postponed.

## 0.1.0-beta.1 — source published 2026-09-23

First public source beta, under the name **Steam Currency Comparer**.
The code was pushed to GitHub on `main`; this was not a tagged GitHub release
or a hosted deployment.

- Local browser interface for comparing public Steam wishlists across Poland,
  the United States, Germany, Norway, and the United Kingdom.
- Selectable baseline and up to two comparison storefronts, with NBP exchange
  rates, regional sale prices, and absolute and percentage differences.
- Wishlist loading orders, filtering, sorting, thumbnails, and CSV export.
- Cached prices and exchange rates, cancellation, retries, and local diagnostics.
- Installation instructions, a detailed usage guide, and live-example screenshots.
- Shared version definition used by the app header, startup message, and health API.

This beta is intended for local use. Public hosting still requires the work
described in [DEPLOYMENT.md](DEPLOYMENT.md).
