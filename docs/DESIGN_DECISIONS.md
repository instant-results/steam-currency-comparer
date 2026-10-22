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
prices. Place the disclosure beside the selection summary, wrapping it below
when space is limited. Update currencies and its help belong inside the expanded
body and disappear when it closes. Empty selections and large currency counts have
explicit summaries. Disclosure uses a native button, aria-expanded, aria-controls
and the hidden attribute; return focus when hiding a focused selector.

Above 600px the two bounded, scrollable picker lists sit side by side. Within
each list, currency cards adapt to available width. At 600px and below the lists
stack, with one card per row and bounded height. Hiding the panel manually discards
unapplied edits and restores the active tab's displayed currencies; before results
exist it restores the choices from opening setup. This also resets remembered
baseline conflicts. Preserve submitted selections during automatic collapse and
while jobs lock controls. Disclosure and discarded drafts start no requests and
never change displayed rows, rates or CSV. Search text survives collapse.

Desktop game identity is 300–480px wide, using spare comparison width after
reserving the baseline, optional credit column, difference and 510px regional
area. At 1000px and below retain the stacked identity/price layout and existing
regional slots. Use the same widths for table headers, rows, sticky copies and
scrollbar boundaries. Artwork retains its current dimensions.

Verify expanded and collapsed states, keyboard disclosure, saved comparisons,
active-job locking, long titles and both catalog credit modes. Check widths on
both sides of breakpoints and 1/2/3/36 alternatives, including best and missing
offers, horizontal scroll extremes and sticky titles.

The sticky storefront-label copy uses the original heading width and rendered
baseline/Difference cell edges. Clip it to that visible currency interval, retain
the original track sizing and scroll offset, and draw matching 2px side dividers
inside the clipped strip. The surrounding scroll surface can be wider than the
table, so its outer edge is not a reliable endpoint for the sticky labels.

## Result filters and display controls

Wishlist Retry comparison belongs beside Compare regional prices in the setup
form, with the same button dimensions and typography and a secondary blue style.
Keep it a non-submit button with its existing retry behavior and visibility rules.
Wrap the pair on narrow screens; the results footer retains the result count.

On wide layouts, place result filters, Show unavailable products and the Steam
best-offers checkbox in the same left-aligned row. Allow the row to wrap as space
narrows; preserve readable labels, checkbox states and accessible associations.
Remove the separate sorting toolbar, including its loading-order note. Headers cycle
ascending, descending and original loading order; no separate Reset sorting
button is needed. Switching columns starts ascending. Use geometric arrows
(12x18px across screen sizes):
arrows: ascending lights the top 40% with a light-blue gradient; descending
lights the bottom 40%; unsorted stays muted. Reflect state in aria-sort and each
button's direction attribute, including the two Difference controls sharing a
header. Center the Game name and baseline-price arrows on the same desktop
header line even when the baseline label wraps.

Replace permanent best-offer explanatory panels with a small blue circular i
button after the label and a blue, rounded popup. The button is independent from
the checkbox. The popup appears near it, stays inside viewport bounds, and keeps
its position if loading changes page height. Center the i with the label text.
Outside clicks and focus changes leave help open. Center the bubble on its i
button, adjusting at viewport edges when opened or resized. Use document positioning
so it scrolls away with the control instead of sticking to the screen. Use a pale-blue
bubble with dark text, generously rounded corners and three spaced paragraphs
with a stronger opening line. A contrasting
blue circular X overlaps the top-right corner; draw its cross geometrically so
it stays centered independently of font metrics. Reserve viewport space around
the overlapping circle and scroll long help inside the bubble. The X, Escape,
or the i button closes it. Opening focuses the X; closing with X or Escape returns
focus to the i button. Keep the same help interaction
for each tab's shared best-offer setting. The owned-library controls remain hidden
under their existing feature flag.

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
