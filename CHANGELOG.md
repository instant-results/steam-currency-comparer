# Changelog

## Unreleased

- Improve backend cache handling during comparisons.

## 0.11.0 — 2026-10-25

- Add Price and Discount loading by the chosen primary offer, preparing and
  reusing all baseline observations before emitting rows. Add Steam Top Selling,
  Release Date and Review Score order for public wishlists, preserving complete
  basic-wishlist membership when Steam's sorted response omits entries.
- Keep a game and its cheaper Steam-selected package/bundle in one paired row.
  The existing checkbox reveals primary-offer radio choices shared across tabs.
  Primary prices drive filters, sorting and statistics; removal and Undo affect
  the whole group. Show a distinct effective discount against the regular game
  price and retain both source offers plus the selected basis in CSV.
- Place display checkboxes in a dedicated row above result filters across
  comparison tabs, with the primary-offer choices beneath their checkbox.

## 0.10.0 — 2026-10-24

- Accept Steam organization homepage aliases, numeric creator homepages and
  developer/publisher search URLs in catalog search fields. Resolve verified credit
  names below the input with explicit Add, reuse existing catalog identities, and
  offer a role-warning popup with an option to open the other tab. Preserve normal
  catalog comparisons, saved selections and recovery behavior.

## 0.9.2 — 2026-10-24

- Add contextual catalog recovery for failed/cancelled/expired comparisons and
  technical partial results, interrupted catalog additions/expansion, and initial
  catalog loading. Retain original currencies and page/selection through reload,
  preserve displayed results and exclusions, and wrap long organization labels.

- Align Wishlist and catalog prompts with their input borders and use the same
  tighter 8px gap above each input, retaining loading-order field alignment.

- Match catalog search forms to Wishlist's background, corner treatment, prompt
  typography and primary-button styling. Bound input widths, align desktop actions
  and use full-width phone actions.

- Match catalog search results to Wishlist's separate results block, coloured
  rows, left-side Add controls and "add to the current comparison" wording.

- Add the five wishlist result filters to each catalog tab, applied within groups
  with separate saved selections. Keep statistics and CSV based on all loaded
  products, and explain empty groups with visible/loaded counts.

- Match catalog credit-column and best-offer checkbox styling and label typography.

## 0.9.1 — 2026-10-24

- Search developer/publisher names after four seconds without edits, with immediate
  Search Steam submission and protection against stale responses. Place Add before
  each match, matching wishlist search.
- Add catalog-header sorting by title, baseline price, absolute difference and
  percentage difference. Cycle ascending, descending and original order within
  each group; remember separate choices for Developers and Publishers.
- Center Load more arrows consistently with compact or separate credit columns.
- Remove entire catalogs through the × on organization icons. Show the organization
  name and role in seven-second Undo notices, preserve shared titles in other
  groups, and retain removals through loading, currency changes and reload.
  Clean private backend memberships, results and selections with bounded retries.
- Put credit-column and best-offer checkboxes together in a wrapping row.
- Place each catalog's search/add step above currency selection and results.

## 0.9.0 — 2026-10-23

- Add games to the wishlist comparison through the existing profile field using
  an App ID, Steam app URL, or selectable name-search results. Search names after
  four seconds without typing and place Add buttons to the left of matches. Start immediately
  when idle and combine only additions already waiting for the current work.
  Preserve previous results during additions, retain selections across reloads
  and currency changes, and support explicit re-addition after removal. Label
  manual rows and append manually_added to CSV without attributing them to a wishlist.
- Separate active-job admission from completed-result retention. Retain at most
  100 completed jobs and 32 MiB of serialized snapshots, subject to one-hour expiry.
  Active jobs are never evicted to make room for old results.
- Remove the three-comparisons-per-minute submission limit so sequential small
  comparisons can start immediately. Retain one unfinished job per connection,
  bounded job storage and queue capacity, and shared Steam request pacing.

## 0.8.0 — 2026-10-23

- Remove individual titles with a circular × overlapping their thumbnail. Exclude
  removed titles from rows, saved results, totals, catalog statistics and CSV
  immediately. Offer seven seconds of Undo in a fixed stack of at most four
  notices, identifying titles and Steam App IDs. Compact the oldest fourth notice
  to 65% height; a fifth removal finalizes it early. Remove every occurrence in
  the current catalog tab, with other tabs independent. Retain removals through
  polling, reload, catalog expansion and currency updates.
- Reveal removal controls with a half-second thumbnail hold on touch devices,
  followed by a separate tap. Cancel holds on movement; hide controls on scroll
  or outside taps. Keep mouse hover and keyboard access. Center Undo notices
  horizontally at the bottom of the screen.
- Retain up to 10,000 removed App IDs per tab, with bounded cleanup batches and
  explicit overflow handling. Retry comparison starts fresh and clears removals;
  currency updates and their retries retain them.
- Count comparison submissions by their creation time so title cleanup does not
  consume the three-submissions-per-minute allowance.

## 0.7.3 — 2026-10-23

- Format currency summaries with commas and a final ", and" for three or four
  alternatives, retaining "and" for two and the storefront count for longer lists.

- Add circular flags near the right edge of baseline and comparison currency
  selection cards. EUR uses the EU flag; its prices still come from Germany.
  Bundle the SVG artwork locally and retain text labels and native selection controls.

## 0.7.2 — 2026-10-22

- Keep offer-help bubbles attached to their information buttons when expanding
  or hiding currency setup, including when the results move offscreen.

- Let Game name absorb unused desktop comparison width so the table reaches
  the right content edge without widening price columns or their padding.

- Remove the redundant Regional Steam Pricing label and decorative dot above
  the headline, with tighter introductory spacing.

- Cycle table-header sorting through ascending, descending and original loading
  order. Remove Reset sorting and its description; use compact arrows with blue
  gradients on the top for ascending and bottom for descending, and align the
  Game name and baseline-price arrows vertically.

- Place wishlist Retry comparison beside Compare regional prices, with matching
  button dimensions and typography; wrap the actions on narrow screens.

- Align sticky storefront labels to the rendered currency-column boundaries,
  preserving both side dividers and preventing overlap into Difference when
  selected currencies fit within a wider comparison surface.

- Remove the redundant final-price caption from wishlist and library footers.

- Group availability and best-offer checkboxes with wishlist filters in a wrapping
  row. Replace permanent offer help panels with blue information buttons and
  pale-blue, rounded popups with spaced text, an overlapping circular close button
  and keyboard support. Keep the bubble and close control within viewport bounds.
  Center help on its information button and let it scroll with the page.
  Help stays open when clicking elsewhere or resizing.

- Place Change currencies beside the selected-currency summary and show Update
  currencies only inside expanded setup. Hiding setup discards unapplied edits
  and restores displayed currencies without starting a job or changing results;
  automatic collapse and locked controls preserve submitted selections.

- Place wishlist completion beside the Games checked count as number · Complete,
  with matching number/status typography. On narrow screens, give Games checked
  its own summary row so the enlarged status stays readable.
  Remove the detached status and empty progress space once processing finishes.

- Move wishlist title search to the spare cell beside currency labels in the
  second table-header row, with a wider bordered field, larger text and a
  full-width layout on narrow screens.

- Add 6px of right-edge breathing room to difference values and storefront
  captions, retaining readable long country labels on desktop and phones.
  Keep the DIFFERENCE heading and sorting controls centered with symmetric padding.

- Move currency selection above the full-width comparison, collapse selectors
  when work starts or results are restored, and retain a summary and disclosure.
  Adapt picker lists to screen width and give desktop game titles more room while
  preserving pinned prices, aligned headings and narrow-screen identity rows.

## 0.7.1 — 2026-10-22

- Recover currency updates when a saved wishlist/example job expires or the server
  restarts. Keep displayed results available while recreating the comparison;
  preserve retry, cancellation and reload behavior.
- Simplify comparison controls: remove decorative action/rate-heading arrows and
  the repeated currency-panel description, compact the comparison button and
  place it beside the profile controls.
- Give small field captions a consistent inset and keep dropdown indicators clear
  of rounded edges. Center filter magnifying glasses and the NBP link arrow.
- Keep a roomy desktop regional area for one/two currencies; center a single
  currency in a slot matching each of the two-currency slots. Center regional and
  difference headings while preserving aligned prices and sticky currency labels.
- Put Cheapest: above the currency/country label to give long country names more
  room on desktop.

- Place the best-offers checkbox directly above each tab's comparison table,
  keeping its help text nearby and synchronizing the shared setting across tabs.

- Align best-offer labels, prices, names and following sale details across each
  game's baseline, regional and difference columns, including wrapped default
  details, original prices, unavailable offers and narrow-screen resizing.

- Keep currency/country column titles visible beneath the sticky scrollbar while
  scrolling through results, synchronized with regional prices and catalog tables.
  Move country codes to the country labels with a middle-dot separator. Show
  converted prices on the left and muted original prices on the right, with
  original-currency codes aligned across rows.

- Move horizontal comparison scrollbars above results, limit their tracks to the
  visible regional columns, and keep them sticky within each comparison section.
  Keep synchronized developer/publisher catalog scrolling. Remove the redundant
  scrolling-arrow buttons and their caption in favor of the top scrollbar.
- Apply a subtle blue treatment to comparison and currency-picker scrollbars.
- Align baseline and converted regional game prices and sale details, using
  matching amount typography on desktop and narrow screens.
- Align the main comparison headings on one level. Keep OTHER STOREFRONTS and
  its conversion caption fixed horizontally, with currency/country labels on a
  separate row below that scrolls together with regional prices.

## 0.7.0-beta — 2026-10-21

- Support 37 live Steam currencies with one representative storefront each and
  one to 36 alternatives. Share the registry between configuration, API and browser;
  add a searchable picker with Select all/Clear. Keep US as the USD representative.
- Pin game/title, baseline and DIFFERENCE while regional columns scroll in aligned
  slots. Synchronize catalog scrolling, retain separate slots for missing best
  offers, and put large catalog statistics in an expandable overview. On narrow
  screens, keep identity above the pinned baseline/difference price edges.
- Validate the additional countries and NBP coverage with public game samples;
  preserve Steam amount scaling, pacing, caching, post-load updates and CSV schema.

- Prepare the exchange-rate backend for post-load currency switching: retrieve
  complete NBP Tables A and B upfront, refreshing only missing or expired tables.
  Cache every validated table rate, including unselected currencies.
- Preserve table-specific source, publication date and retrieval age through
  live/cache/stale results. Commit table observations atomically and migrate
  existing caches to schema 9 without changing Steam price data.
- Keep successful table retrievals when the other table fails, and allow comparisons
  whose required rates are available to proceed. Reject
  malformed tables and stop on local network denial.
- Add a backend currency-change endpoint for completed comparisons. Reuse the
  loaded games, their order and catalog membership without repeating discovery;
  retrieve only missing or expired selected-country observations using the existing
  default-price and best-offer caches. Keep the original result available while
  a separate, cancellable job computes the new comparison.
- Keep capability-token access, shared worker limits and per-comparison currency
  change locking. Additional supported storefronts are listed in docs/STOREFRONTS.md.
- Add explicit post-load **Update currencies** for the current wishlist/example,
  Developers or Publishers tab. Retain the displayed comparison during updates,
  swap complete/partial snapshots together and preserve it on failure/cancellation.
- Preserve view settings, catalog groups and storefront-specific pagination context.
  Restore displayed and pending state separately on reload; keep CSV tied to the
  displayed currencies and lock competing starts until updates finish.

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
