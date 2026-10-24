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

Desktop game identity normally uses 300–480px, expanding beyond that range to
fill spare width when all selected storefronts fit. Calculate its width after
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

When all selected storefronts fit on desktop, let the Game name column grow
beyond its normal 480px limit to fill unused comparison width. Preserve the
usual identity widths when regional columns overflow, and retain fixed baseline,
storefront and Difference widths. Share the region count with the scrollbar
surface so pinned offsets and scrollbar padding follow the expanded identity.

## Title removal and Undo notices

The remove button is a circular blue × overlapping the thumbnail's top-right
corner by 10px. Use the existing offer-help close-control palette and geometric
cross; keep it independent from Steam artwork/title links. Reveal it on thumbnail
hover and keyboard focus. Preserve the artwork dimensions, comparison column
widths and credit alignment.

Touch removal uses a 500 ms thumbnail hold to reveal the control, followed by a
separate tap to remove. Movement cancels the hold; scrolling and outside taps
hide the control. Mouse hover and keyboard focus remain supported.


Use the established pale-blue bubble palette, dark text, rounded corners and
blue buttons for Undo notices. Fix one shared stack near the viewport's
bottom center, with safe-area and narrow-screen clearance. Show the title, Steam
App ID and a separately labelled Undo button. Keep text and targets full size:
the oldest fourth notice uses 65% of the standard 100px height rather than scaling
its contents. The other three notices retain standard height. A fifth removal
finalizes the oldest notice. A seven-second countdown strip is decorative;
reduced-motion mode omits its animation. Hover/focus never pauses expiry.

Remove rows, CSV data and statistical contributions immediately. Undo restores
every occurrence within the current tab and original loading positions while
respecting current filters/sorts. Use one stack across the three visible tabs,
with independent removal state per tab. Do not add the feature to the deferred
owned-library interface.

Verify mouse, keyboard and touch access, table alignment, long titles, duplicate
catalog memberships, independent deadlines, rapid fifth removals, late results,
empty comparisons, reload, CSV and currency-update behavior. Keep the Undo buffer
out of session storage and release row references at finalization.

## Currency picker flags

Display a 24px circular flag at the end of every baseline and comparison card,
vertically centered with 12px of space to the right border. Reserve its width in
the flex layout so long currency/country captions wrap without overlapping it.
Use the same size and placement across desktop and narrow layouts.

EUR uses the EU flag; the visible Euro / Germany caption continues to identify
Germany as the representative storefront. Other flags follow the representative
country. Flags are decorative SVGs, hidden from assistive technology and excluded
from keyboard focus. The native radio/checkbox and the full clickable label
retain their existing behavior. Bundle one local SVG sprite to avoid a request
per flag. Keep the original SVGs, source revision and MIT license in web/flags/;
no flag CDN is needed at runtime. Rebuild web/flags.svg with
`python tools/build_currency_flags.py` after changing the source artwork.

## Result filters and display controls

Wishlist Retry comparison belongs beside Compare regional prices in the setup
form, with the same button dimensions and typography and a secondary blue style.
Keep it a non-submit button. Retry comparison starts fresh and clears removals;
Retry currency update preserves the current selection and its removals.
Wrap the pair on narrow screens; the results footer retains the result count.

On wide layouts, place result filters, Show unavailable products and the Steam
best-offers checkbox in the same left-aligned row. Allow the row to wrap as space
narrows; preserve readable labels, checkbox states and accessible associations.
Remove the separate sorting toolbar, including its loading-order note. Headers cycle
ascending, descending and original loading order; no separate Reset sorting
button is needed. Switching columns starts ascending. Use 12x18px geometric
arrows across screen sizes: ascending lights the top 40% with a light-blue gradient; descending
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

Choose the bubble's side and viewport clearance when opening. Preserve that
placement relative to the information button during layout changes, including
currency-panel expansion/collapse. Refit on viewport resize only when the button
is visible; an offscreen button carries the bubble offscreen with the results.

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

## Individual game additions

Use the existing profile field for a public profile, game App ID, Steam app URL
or game name. Change its submit label to match the detected input. Name matches
appear below as text with product type and App ID, with an Add button on the left.
Search names after four seconds without typing; reset the timer on each edit,
discard stale responses, and keep explicit submission for profiles and App IDs.
Keep the field usable during loading so additional selections can be queued.
Start immediately while idle; batch only already queued selections. Do not add a
debounce window to delay price comparisons. Keep prior results visible while the
new selection is compared, and use its displayed currencies. Mark manual rows
without introducing a new table column. Keep long matches wrapping at narrow widths.

## Catalog search results

Developer and publisher matches use an Add button before the name, in visual
and keyboard order. Keep the action on the left on phones and let long names
wrap beside it. Adding a catalog still starts its price comparison.

## Catalog sorting

The shared catalog header uses the wishlist sort controls and direction indicators.
Sort each group independently without changing membership or group order. Retain
original discovery order for the third click and exports. Developers and Publishers
remember separate sorting choices; sorting starts no requests.
