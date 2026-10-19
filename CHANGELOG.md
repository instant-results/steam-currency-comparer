# Changelog

## 0.6.2-beta — 2026-10-20

- Automatically compare the seven-game example on a fresh visit and remove the
  redundant example button. Restore existing wishlist comparisons first; typing
  a profile dismisses a pending example. Failed examples use the existing retry.
- Centralize frontend job coordination across wishlist, developer, publisher and
  internally enabled library comparisons. Reconnect hidden saved catalog jobs
  before automatic work; defer examples until the wishlist is visible and idle.
- Replace catalog auto-start polling with shared idle scheduling. Keep active
  comparisons, selected currencies, cancellation and per-tab results independent.

## 0.6.1-beta — 2026-10-19

- Floor calculated discount percentages to whole points and mark them with ≈;
  preserve suitable Steam-provided percentages. Hover text identifies the source.
- Retain calculated-discount provenance in caches, comparisons, and CSV exports.
  Sales below 1% retain their sale status and shorter cache lifetime.

## 0.6.0-beta — 2026-10-18

- Batch regional default prices through appdetails and metadata/best offers through
  StoreBrowse. Use the same pipeline for every list size, with configurable
  100-item limits, a 6,000-byte URL budget, bounded recovery and shared pacing.
- Cache metadata and best offers separately from game prices; retain cancellation,
  stale-price labels, ordered progress, and compatible existing price caches.
- Add a shared checkbox for separately labeled Steam-selected packages/bundles.
  Preserve default comparisons, offer identities, partial observations and exports.
- Prefer Steam's percentage when consistent with the same offer's regular/current
  prices; calculate only a missing or inconsistent percentage. Leave bundle and
  compliance-only regular-price discounts unknown instead of borrowing game prices.
- Add best_offer_* CSV fields after existing columns. Shared batch request counts
  are attributed once per window; they include price, metadata and offer attempts.
- Measure one cold 200-game run per version: 815.194 seconds before, 20.664 seconds
  after, with 534 versus 12 Steam data requests. First delivery changed from 4.897
  to 10.931 seconds. See docs/STEAM_PRICE_PERFORMANCE.md for coverage and limitations.
- Keep automatic examples, dynamic currency changes and dropdown alignment deferred.

## 0.5.0-beta — 2026-10-14

- Retain an internal Owned library prototype immediately after Your wishlist when
  explicitly enabled for QA, with the same row renderer,
  credits, prices, filters, sorting, unavailable toggle, cancellation, and retry.
- Add retrieval code for visible owned games through Steam's GetOwnedGames API with a server-side
  Web API key. Support numeric and custom profile URLs, Name/Steam loading orders,
  explicit empty/unavailable libraries, missing/rejected keys, and the 1,000-game limit.
- Keep library results, filters, currencies, and job access independent in tab
  storage; share worker locking, storefronts, exchange rates, and price caching.
- Extend the shared CSV with source_tab=library and additive library_profile and
  library_loading_order columns. Library attribution is off by default; existing
  wishlist and catalog columns retain their names and positions.
- Compare current storefront prices, exclude free-to-play games from retrieval,
  and document that owned games are not a complete license/DLC inventory.

- Hide the tab/profile form and disable library initialization, saved-job reconnect,
  and job submission by default. Preserve stored state; visible tabs keep their
  navigation, currency choices, and existing comparison behavior.
- Defer successful authenticated API-key/library live testing until Steam Guard
  access is available. Record the TODO checklist; the owned-library stage is not
  complete. Existing automated/sample checks are retained.

## 0.4.7-beta — 2026-10-13

- Show compact Developer and Publisher lines beneath the artwork/title in
  wishlist rows, including all reported names and missing-metadata labels.
- Align both credit-name lists in a shared fluid grid. Record wording, typography,
  and future translation boundaries in docs/TEXT_AND_LOCALIZATION.md.
- Reuse catalog credit typography and cached appdetails metadata without extra
  requests to display credits. Preserve table columns, sorting, filters, artwork,
  and the unified CSV; catalog credit-column modes retain their own behavior.

## 0.4.6-beta — 2026-10-13

- Use one fixed, versioned CSV schema for Wishlist, Developers, and Publishers,
  including both credit lists, catalog membership, and a wishlist-profile column
  whose values remain blank unless attribution is enabled.
- Add comparison storefronts, Steam links, individual price sources, converted
  base prices, per-storefront differences, cheapest alternatives, failure details,
  request/cache counts, and flags distinguishing unknown from empty credit lists.
- Refresh older wishlist price-cache entries missing credits on comparison;
  subsequent comparisons reuse the enriched cache. Exporting adds no requests.

## 0.4.5-beta — 2026-10-13

- Close out the developer/publisher feature branch with its implemented searches,
  catalogs, compact/column credits, and CSV downloads.
- Record the next targets in docs/ROADMAP.md: CSV format unification across tabs
  and compact developer/publisher descriptions on wishlist rows, followed by an
  owned-library tab. These changes are planned, not implemented in this version.

## 0.4.4-beta — 2026-10-11

- Rename catalog checkboxes to Show publisher column / Show developer column.
  Checked shows a separate labeled column; unchecked retains compact credits
  beneath game titles. Each tab saves its display mode independently.
- Keep shared headers, price dividers, statistics, and narrow-screen scrolling
  aligned in both layouts. CSV exports always retain both credit fields.

## 0.4.3-beta — 2026-10-11

- Add Download CSV below each developer/publisher catalog list, exporting checked
  products with price, discount, conversion, and provenance fields. Both credit
  columns are always included, independently of the display checkbox.
- Identify each exported catalog by role and name; retain separate membership
  rows for products present in more than one selected catalog.

## 0.4.2-beta — 2026-10-11

- Add independent Show publisher / Show developer checkboxes above catalog searches.
  Credits appear below each game title and the display choice persists per tab.
- Cache Steam product credits alongside prices; refresh older catalog results and
  cache entries once to supply missing metadata.

## 0.4.1-beta — 2026-10-11

- Feature Devolver Digital (US), THQ Nordic (Austria), and 11 bit studios (Poland) as publishers, with games developed by different studios.
- Add Polish developer Techland with Dying Light, Dying Light 2, and Call of Juarez: Gunslinger.
- Curate publisher examples independently of developer self-publishing roles.
- Replace retired defaults in saved sessions while retaining user-added catalogs and their cursors.

## 0.4.0-beta — 2026-10-11

- Split Developers and Publishers into separate tabs with role-specific searches and catalogs.
- Remove the Creator category and homepage catalog option from the interface.
- Keep independent catalog selections, results, pagination, and search controls for each role.
- Expand featured entries through exact-name developer/publisher product credits.
- Migrate explicit role selections from the combined tab and preserve shared comparison locking.

## 0.3.1-beta — 2026-10-03

- Group creator search results into one row per name with descriptive catalog buttons.
- Verify developer and publisher catalogs before offering those roles, including for suggested names.
- Wrap catalog buttons on narrow screens and retain independent selection states.
- Handle Steam search returning its default 25-entry pages despite a smaller requested page size.

## 0.3.0-beta — 2026-10-03

- Search Steam creator homepages by name and add catalogs beside the featured three.
- Exact-name Developer and Publisher catalog fallbacks, with separate identities.
- Bounded discovery caching, validated selectors, and restored dynamic creator groups.
- Preserve the existing comparison pipeline, statistics, pagination, and table alignment.
- Research notes cover API probes, prior implementations, limitations, and a deferred local-directory TODO.

No tag, push, GitHub release, or deployment was created.

## 0.2.0-beta — 2026-10-03

First beta of the 0.2 development milestone, adding developer and publisher catalog comparisons.
This version has not been tagged, published as a GitHub release, or deployed.

- Developer and publisher tab with featured creators, icons, and regional price
  comparisons for three selected games per creator.
- Expandable Steam catalogs, shared price caching, cancellation, refresh of
  displayed products, and separate saved results for each tab. Creator search
  is postponed.
- Hide free products, including demos, after checking, while retaining paid
  products with missing prices and paid DLC/soundtracks.
- Creator identity rows above games, with average and median percentage
  differences per comparison currency, sample sizes, and coverage of loaded products.
- One shared column-heading row, aligned statistics and foreign-price slots,
  and synchronized horizontal scrolling on narrow screens.
- Centered flat-topped Load more arrow with a soft blue gradient, extra top-center
  transparency, white label, and no visible border. The 1px price divider aligns
  with its midpoint, extends through pending and appended rows, and stops at
  80% of the last row; the final horizontal rule is removed.
- Compact creator introduction with consistent text sizing, no redundant currency
  or catalog descriptions, and a separate statistics exclusion note.
- Currency setup numbering follows the active tab. The featured-games footer
  label is limited to the curated selection and remains absent after catalog
  expansion, baseline changes, and restoring saved results.

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
