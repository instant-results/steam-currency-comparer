# Text and localization decisions

Updated: 2026-10-21. This is the current reference for user-facing wording,
typography, and text alignment. Update the relevant decision when changing copy
or its presentation. English is the current interface language; a translation
system and language selector have not been implemented.

## Product credits

Wishlist and owned-library credits appear below the game's artwork/title, in this order:

| Meaning | Current English text |
| --- | --- |
| Developer role label | Developer: |
| Publisher role label | Publisher: |
| Metadata still pending | Loading… |
| Metadata missing or an empty reported list | Unavailable |

These labels identify roles, so they remain singular even when multiple names
follow. Show all names reported by Steam in their supplied order. The current
English UI separates names with a comma and a space. Company names, product
titles, trademarks, and Steam App IDs are source data, not translatable UI copy.
Display source names as text; never interpret them as HTML.

Unavailable means that credit information is not available to display. It does
not claim that the product has no developer or publisher. Loading… applies to
pending metadata, not completed results with missing credits.

Developers catalogs show Publisher: credits; Publishers catalogs show Developer:
credits. Their optional credit-column mode uses the corresponding role heading.
Wishlist and owned library show both roles together.

## Credit alignment and typography

- Role labels and names occupy separate columns in a shared grid per wishlist/library
  game. Developer and publisher names start at the same position.
- Size the label column from its content, capped at 45% of the credit block.
  The names column uses the remaining space and allows wrapping. Long localized
  labels may wrap too; no width depends on the length of an English word.
- Wrapped names stay in the names column rather than restarting beneath a label.
  Keep all labels/names in reading order: developer label, developer names,
  publisher label, publisher names.
- Use the existing small, muted catalog-credit typography and spacing.
  Keep credits beneath the whole artwork/title link. They are supplementary
  information, not additional price-table columns.
- Use CSS grid/gaps and logical start alignment. Do not align text with padded
  spaces, nonbreaking-space runs, fixed character counts, or label-specific
  offsets. Preserve table-header/cell alignment and horizontal scrolling.
- Narrow layouts must wrap names within the credit block without widening the
  page. When adding right-to-left languages, set document language/direction and
  verify reading order and logical alignment in a browser.

Implementation: web/app.js (comparisonRow) and web/app.css
(.wishlist-credits). Catalog compact styling remains .catalog-credit.

## Currency-update wording

Use **Update currencies** for the explicit action on a completed comparison in the
current tab. **Displayed: PLN against USD and EUR** identifies the snapshot in use;
sidebar choices can differ while the user prepares another selection. Pending
progress names the requested currencies without changing displayed price labels.
**Retry currency update** repeats a failed or cancelled selection. **Reload wishlist**
is used when an expired source job requires a new initial comparison.

Keep these captions in the existing hint typography. The sidebar action uses the
existing primary-button styling and a wrapping caption. Preserve column-header/cell
alignment, horizontal table scrolling and both compact and separate credit layouts.

## Many-currency comparisons

Use **Find a currency or country**, **Select all**, and **Clear** for selection.
Use **Scroll other storefronts horizontally** as the top scrollbar's accessible
label. Headings pair a currency code
with its representative country; USD means United States and EUR means Germany.
For more than four alternatives the compact displayed caption gives the baseline
and storefront count; actual column headings and CSV retain every selected code.

Keep the existing column order and typography. Pin game/title and baseline on the
left and DIFFERENCE on the right; regional headings and both offer sets use the
same ordered slots. On narrow screens put identity above the price row, keeping
baseline and DIFFERENCE at its edges. Missing observations occupy their regional
slot rather than shifting other prices. The overall difference identifies the
cheapest selected storefront. Large catalog metrics use **Regional statistics**.

Use two header levels. On desktop, vertically centre GAME NAME, the baseline
heading, OTHER STOREFRONTS and DIFFERENCE in the same main heading row. Keep OTHER
STOREFRONTS and its conversion caption fixed horizontally within the visible
regional area. Put individual currency/country labels in a separate row below,
scrolling with the corresponding prices. Keep each country below its currency.
When this label row reaches the sticky scrollbar, retain its currency/country
titles immediately below the scrollbar until the comparison ends. Match its
column widths, typography and horizontal offset to the original labels and prices;
use the same behavior when no horizontal scrollbar is needed. Retain original
accessible table labels and keep any visual copy hidden from assistive technology.
Use 5px vertical padding in the sticky title copy (rather than the normal 10px)
to reduce its height without shrinking either text line.
Country codes now follow country names in both normal and sticky titles,
separated by a middle dot with a space on either side (United States · US).
Remove the country-code prefix from default and best-offer price rows. Keep the
converted price at the start and show the original price in the existing muted
12px country-code styling at the end. Keep the original currency code at the
same right edge across rows. Original amount and code form one unit that can
wrap together below the converted price when space is limited. Do not change
comparison arithmetic, sale-note currencies, or CSV values.

Best-offer blocks share their label, value and name bands across a game's
baseline, regional and difference cells. Compensate for wrapped default details
before the best-offer label; align the best-offer amounts and the sale details
following offer names. Missing or subscription offers retain their value slot.
Measure actual wrapping after render/width changes so bands can shrink as well
as grow, preserving original-price alignment and the existing default-offer view.
On narrow screens retain the identity/credit rows above the price headings and
reserve enough space below wrapped group labels for their conversion caption.

The horizontal scrollbar sits above each comparison and spans only the visible
regional columns, excluding pinned identity, optional credits, baseline and
DIFFERENCE. Keep it sticky at the viewport top within that comparison section.
Use a muted blue thumb and dark blue track for this scrollbar and the vertical
currency pickers. The redundant scrolling-arrow buttons and caption are removed;
the native scrollbar and table retain keyboard navigation.
Baseline and converted regional game amounts share font family, size, weight,
line height and vertical starting position; their sale notes start together too.
Keep compact country labels inline with amounts on narrow screens.

## Owned-library wording

These decisions apply to the internal prototype. Its tab and profile form are
hidden by default pending authenticated live QA; do not advertise it as available.

Use Owned library for the tab immediately after Your wishlist. The table uses
Your library comparison. Name is the default loading order; Steam order means
the order returned by the API, not purchase date, playtime, or wishlist priority.
Explain that these are current storefront prices, not historical purchase prices.
Keep missing credentials and unavailable Game details distinct from an explicitly
empty library. Include library profile is opt-in and off by default.
The required server-side key setup is explained next to the profile input; bound
its text beside/below the comparison button so it cannot squeeze the input.
The wishlist row renderer and existing credit/table styles are shared, including
narrow-screen scrolling and matching header/cell boundaries.

## Wording and translation boundaries

- Prefer concise, plain, sentence-case labels and complete explanatory sentences.
  Table headings may retain their established uppercase visual style.
- Role and state labels are translatable; supplied company names are preserved.
  Translate the complete label, including punctuation appropriate to the locale.
  Preserve the Unicode ellipsis in the current English loading label.
- When a translation layer is introduced, use stable message keys and named
  placeholders for complete messages. Avoid building translated sentences by
  concatenating English fragments. Candidate credit keys are
  credits.developer_label, credits.publisher_label, credits.loading, and
  credits.unavailable; these are proposed keys, not existing runtime APIs.
- Use locale-aware display formatting for lists, dates, and numbers when adding
  languages. Currency codes and storefront identity must remain explicit:
  Germany is the selected EUR storefront, not every EUR storefront.
- Keep the public product name Steam Currency Comparer and existing technical
  package/environment-variable names consistent with README.md.

## CSV and technical identifiers

UI translation must not silently translate API keys, enum values, session-storage
keys, region/currency codes, CSV column names, or CSV schema identifiers.
CSV schema 1 remains a stable analysis format: decimal points, true/false,
UTC timestamps, and semicolon-separated credit lists. Preserve source names,
missing-value semantics, and spreadsheet formula escaping. See
[USAGE.md](USAGE.md#shared-csv-schema).

## Verification when text changes

Check long names, multiple names, missing/pending metadata, desktop and narrow
layouts, and table-column alignment. Translation work should additionally check
long localized labels, non-Latin text, right-to-left reading order, and the
language/direction metadata. Record meaningful wording/layout decisions here;
keep implementation history in Git and CHANGELOG.md.
