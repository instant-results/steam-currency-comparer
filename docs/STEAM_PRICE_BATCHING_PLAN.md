# Steam price batching — implemented design

Updated: 2026-10-18. Branch: `codex/steam-price-batching`, version `0.6.0-beta`.
Research and limits: [STEAM_PRICE_BATCHING.md](STEAM_PRICE_BATCHING.md).
Measured before/after results: [STEAM_PRICE_PERFORMANCE.md](STEAM_PRICE_PERFORMANCE.md).

## Retrieval and sizing

Every nonempty web comparison uses the same hybrid batch pipeline, including a
single game. Wishlist, example, catalog, and internally enabled library jobs use
it. The legacy command-line provider remains compatible; it is not a small-list
optimization path selected by web jobs.

`BatchPolicy` configures metadata size (100), price size (100), encoded full-URL
budget (6,000 bytes), logical recovery calls (7 including the original), and
physical attempt budget (21 including retries). `JobManager(batch_policy=...)`
accepts an override; no user-facing settings or environment variables were added.
The planner deduplicates IDs stably and never issues empty batches. One country
per request; neither endpoint aggregates several countries in one call.

The current version always retains both price interpretations so the display
checkbox needs no additional requests. Per window and country it requests:

1. appdetails with only `price_overview`, preserving the default game offer.
2. StoreBrowse `GetItems`, with basic info and Steam's best purchase option.

Cold data therefore needs approximately `2 × countries × windows` requests,
subject to URL limits, cache misses and recovery. This supersedes the earlier
`countries + 1` estimate for a metadata-only hybrid without regional best offers.
For 100 games across five countries, the new dual-offer floor is ten data
requests; for the measured 200 games across three countries, it is twelve.

## Validation and recovery

Match results by app ID, never array position. Duplicate StoreBrowse IDs, missing
items, wrong item types, invalid prices/currencies and malformed response shapes
cannot silently shift observations. Valid siblings are retained. A successful
empty appdetails data array means no price supplied, not a free game. Free status
comes from successfully retrieved StoreBrowse metadata.

Only malformed/incomplete responses and HTTP 400/414 shrink into smaller groups.
Normal transient retries run first; 429/5xx/TLS/local-denial failures do not cause
split storms. Split children share both budgets. Rate-limit Retry-After delays
also apply after the final failed attempt, and pacing waits are cancellable.
Permission denial stops the job. Completed country/batch observations remain
cached if later work fails or is cancelled.

## Cache and progress

Schema 7 adds independent regional metadata and offer observations. Existing
price/rate tables remain compatible. Metadata is English and country-contextual,
with a 24-hour TTL. Offers, including known absence, have a 15-minute TTL.
Default prices retain one hour normally, 15 minutes on sale, one hour for missing
prices, and six hours for unavailable apps. Fresh legacy prices can be enriched
without resetting their fetch time. Missing credits are known empty lists after
a successful metadata response; unrequested/failed metadata remains unknown.
Restricted metadata cannot overwrite a known successful record.

Default prices and best offers may use labeled stale observations on temporary
errors. Local denial cannot be hidden by stale fallback. No profile-to-game or
ownership mapping enters the shared cache. Job-local results retain both offer
sets, including available best offers from incomplete regional comparisons.

Your Rank and Date Added prepare bounded windows, then emit rows in order. Name
order first resolves metadata for sorting and reuses the resulting observations.
Physical Steam data attempts are charged once to the first emitted row in each
window; name-prefetch attempts join the first window. Cache-hit fields still count
item-country observations. The legacy `live_price_requests` CSV field now includes
metadata and best-offer requests; it must not be summed across repeated regional
CSV rows without deduplicating games/windows. Wishlist/NBP calls are not included
in that per-row field. The benchmark independently counts all physical calls.

## Two price interpretations

Default offers continue to drive game filters, sorting, totals and catalog
statistics. The shared checkbox reveals a separately calculated comparison of
Steam-selected offers. It preserves package/bundle IDs, names, prices and source
labels, persists in tab storage, and works across comparison tabs. CSV always
retains both datasets in separate fields, regardless of checkbox state.

StoreBrowse prices have no explicit currency code in the observed schema.
Their currency is attributed to the requested supported storefront and that
basis is retained in results, tooltips and CSV. An appdetails currency mismatch
also blocks the corresponding best offer. This is not an independent currency
code validation of StoreBrowse. Current support remains the existing five pairs;
additional real storefronts require validation before enabling them.

A best offer is Steam's anonymous selection, not a personalized checkout quote.
Bundles can differ by country and existing ownership. Recurring subscription
options are explicitly unsupported. The discount metric is `(regular-current) /
regular × 100`, rounded to two decimals, for the same offer. Compliance-only
reference fields never supply that regular baseline. Bundle regular-price
percentages remain unavailable because component savings are not proof of a
regular bundle price. Current offer prices and regional comparisons remain usable.

## Verification and remaining scope

Deterministic tests cover planner limits, one/200 items, five and six storefronts,
empty/reordered/missing/duplicate responses, currency errors, free/restricted apps,
cache reuse and legacy enrichment, stale fallback, cancellation, shared attempt
budgets, throttling, request accounting, and both offer calculations. UI tests
cover toggling without requests, retained default values, credit columns, exports
and refresh. The live benchmark is one run per version, not a repeated load test.

The historical benchmark baseline is preserved by its pre-change commit; an
isolated process imported the original modules for measurement. Raw responses,
benchmark selection, caches and UI fixtures stay ignored. Research documents were
committed before implementation, feature changes as `97a5c98`, and tests as
`88cb5de`, with delivery documentation separate. This batching stage is complete;
see [project context](../PROJECT_CONTEXT.md) for current integration status and
[the roadmap](ROADMAP.md) for remaining work. Owned-library enablement remains deferred.


Discount percentage preference: retain Steam's reported percentage when it agrees
with the known regular/current price relationship, allowing whole-percent rounding
or truncation and one minor unit of price rounding. Calculate a replacement only
when the percentage is missing or inconsistent. A known regular price is required;
compliance-only references and ambiguous bundle bases still remain unavailable.
The same rule applies to live default prices, cached prices and eligible best offers.
Previously cached calculated percentages cannot recover an overwritten upstream
value; ordinary cache expiry refreshes them without extra requests for this change.
