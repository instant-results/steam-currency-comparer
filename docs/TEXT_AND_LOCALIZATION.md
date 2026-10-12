# Text and localization decisions

Updated: 2026-10-13. This is the current reference for user-facing wording,
typography, and text alignment. Update the relevant decision when changing copy
or its presentation. English is the current interface language; a translation
system and language selector have not been implemented.

## Product credits

Wishlist credits appear below the game's artwork/title, in this order:

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
Wishlist shows both roles together.

## Credit alignment and typography

- Role labels and names occupy separate columns in a shared grid per wishlist
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
