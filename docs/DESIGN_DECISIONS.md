# Frontend design decisions

This document records accepted visual choices and their intended scope. Update
the relevant decision when changing the design; keep implementation history in Git.
See [text and localization decisions](TEXT_AND_LOCALIZATION.md) for wording,
credits, comparison-table typography and translation boundaries.

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

Browser checks at 1920px and 390px confirmed the four visible caption types have
the same 6px inset, with unchanged input text padding and no page overflow.
Dropdown keyboard selection passed. The 122 frontend tests and 22 focused
web-application tests passed. Synthetic preview data and screenshots remain in
ignored local QA storage.
