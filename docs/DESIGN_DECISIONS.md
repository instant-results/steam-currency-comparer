# Frontend design decisions

This document records accepted visual choices and their intended scope. Update
the relevant decision when changing the design; keep implementation history in Git.
See [text and localization decisions](TEXT_AND_LOCALIZATION.md) for wording,
credits, comparison-table typography and translation boundaries.

## Currency setup and comparison width

Currency selection occupies a full-width panel above the comparison, shared by
wishlist, developer and publisher tabs. It does not reserve a sidebar beside rows.
The panel starts expanded until a comparison starts or saved results are restored.
Each new run collapses the selectors once. Change currencies can reopen them even
during a run, while the existing job lock keeps selections disabled. Completion,
polling and tab changes do not repeatedly close a manually reopened panel.

Keep Selected: distinct from Displayed: so editing the setup never relabels saved
prices. The summary, disclosure and existing Update currencies action remain
outside the collapsed body. Empty selections and large currency counts have
explicit summaries. Disclosure uses a native button, aria-expanded, aria-controls
and the hidden attribute; return focus when hiding a focused selector.

Above 600px the two bounded, scrollable picker lists sit side by side. Within
each list, currency cards adapt to available width. At 600px and below the lists
stack, with one card per row and bounded height. Search and selections survive
collapse; disclosure alone starts no requests.

Desktop game identity is 300–480px wide, using spare comparison width after
reserving the baseline, optional credit column, difference and 510px regional
area. At 1000px and below retain the stacked identity/price layout and existing
regional slots. Use the same widths for table headers, rows, sticky copies and
scrollbar boundaries. Artwork retains its current dimensions.

Verify expanded and collapsed states, keyboard disclosure, saved comparisons,
active-job locking, long titles and both catalog credit modes. Check widths on
both sides of breakpoints and 1/2/3/36 alternatives, including best and missing
offers, horizontal scroll extremes and sticky titles.

## Wishlist title search

Place wishlist search in the spare game cell of the second header row, beside
the individual currency/country labels. Keep Game name sorting in the main
heading row above. Use the game column's available width, a visible
border, 14px input text and a 44px field height. The input keeps its accessible
filter label and a single focus outline around the whole field, including its
magnifying glass.

Keep desktop primary column headings vertically aligned at their compact
height. In the narrow stacked layout, search spans the visible table width
below the main price headings and above currency labels. Price headings align even when storefront
names wrap. Horizontal regional scrolling must leave search pinned with identity.

Typing and clearing filter loaded rows only; they do not start requests, change
sorting or discard results. Keep the input available when no titles match and
retain keyboard focus while rows rerender. Library and catalog controls retain
their existing layouts.

## Small labels above input fields

Accepted: 2026-10-22.

Place small field captions **6px inward from the field's outer start edge**.
Use the shared `.field-caption` class and logical `padding-inline-start`.
Keep the field border, width, input padding and existing font styles unchanged.

The caption sits between the border and the input text. This provides a modest
visual indent while keeping the caption distinct from the value below. Exact
alignment with the input text made Loading order appear too far inward; alignment
with the border made related search labels inconsistent with the revised dropdown.

| Caption | Where it applies | Input text inset, including border |
| --- | --- | --- |
| Loading order | Wishlist dropdown and hidden library dropdown | 13px |
| Find a currency or country | Shared currency search | 11px |
| Find a developer | Developers search | 13px |
| Find a publisher | Publishers search | 13px |

The 6px caption inset applies on desktop and narrow screens. It does not require
all inputs to have identical text padding. Developer/publisher labels retain their
existing heavier font style.

For a label wrapping an input, put the caption in its own span so the inset does
not move the input. Existing label associations, accessible names, native select
behavior and keyboard interaction remain intact. The library form stays hidden
under its existing feature flag.

Large profile prompts, section headings, currency-group legends, checkboxes and
inline result filters are separate patterns. Do not apply this inset globally to
every label or use text spaces to produce the alignment.

### Verification

Check desktop and narrow layouts for a consistent 6px caption inset, unchanged
input text padding and no page overflow. Verify label associations and dropdown
keyboard behavior. Keep the library control behind its existing feature flag.
