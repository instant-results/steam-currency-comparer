# Changelog

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
