# Steam price batching - backend investigation

> Research snapshot, completed before implementation. Version 0.6.0-beta now
> fetches both default prices and regional Steam best offers. Its request floor
> is twice the country count per window, rather than the metadata-only hybrid's
> country count plus one. See [implemented design](STEAM_PRICE_BATCHING_PLAN.md)
> and [measured performance](STEAM_PRICE_PERFORMANCE.md).


Verified: 2026-10-18 (Europe/Warsaw). Branch: `codex/steam-price-batching`.
Status: research and implementation planning only; application code, UI, and cache schema are unchanged.
See [implementation plan](STEAM_PRICE_BATCHING_PLAN.md) for the proposed work sequence.

## Recommendation

Use a hybrid pipeline initially: batch game metadata through
`IStoreBrowseService/GetItems/v1/`, then batch `appdetails` price_overview
requests separately for each requested country. Preserve the existing appdetails
price definition, explicit currency verification, base price, and discount fields.
Use one hybrid retrieval pipeline for every list size, including a single game.
The existing individual appdetails lookup may remain only as a bounded recovery
fallback for missing metadata or incompatible responses, not a small-list optimization. Do not silently substitute StoreBrowse's best
offer for an appdetails price.

Design the retrieval layer for an arbitrary ordered collection of supported
storefronts. Its batch size should limit games per request, not countries per row.
The current UI/API selection limit remains unchanged in this backend stage.

## Evidence and limits

Anonymous, cookie-free, key-free HTTPS GET probes were run sequentially with a
1.5-second pause before each request. No rate-limit stress test was performed.
Temporary scripts and full public responses remain ignored under
`.steam-price-polisher/qa/batching/`. No user wishlist/profile was used.
The probe timestamps are UTC on 2026-10-17; the local research date is 2026-10-18.

Both endpoints returned all 25 requested item records for each of PL, US, DE, NO,
and GB. This is 125 item-country observations per endpoint, not 125 priced offers:
119 were paid offers, five were Dota 2/free, and Dying Light was unavailable in DE.
The sample includes a paid DLC and soundtrack. A separate mixed sample verified
that invalid IDs did not prevent valid IDs from returning.

The 25 public sample IDs, drawn primarily from existing example/featured lists:

```text
1145360, 237930, 107100, 1091500, 292030, 20920, 239140, 534380,
204450, 1313140, 460950, 311690, 228380, 610370, 1084160, 606150,
330020, 731040, 413150, 640820, 1245620, 367520, 570, 2138330, 1206340
```

The five-country equivalence checks used 25-item batches. Subsequent size probes
used distinct public chart/search IDs, with completeness checked by ID:

| Interface/mode | Successful observations | Failed observations |
| --- | --- | --- |
| appdetails price-only | 50, 100, 150, 175, and some selections up to 200 items | Other selections failed around 197-200; 250 failed. Failures included HTTP 500 and HTTP 200 with an empty body. |
| StoreBrowse basic info + best option, ordinary URL encoding | Up to 250 items | 300 failed with an HTTP 400 edge response. |
| StoreBrowse metadata only, compact URL encoding | 300 and 305 items | 310 returned HTTP 414. The successful 305-item URL was 8,095 bytes; the failed 310-item URL was 8,225 bytes. |
| StoreBrowse form POST | None | The tested read-only GetItems request returned HTTP 405. |

There is no verified universal item maximum. Appdetails failures were not explained
by item count or URL length alone: alternate IDs/country allowed a 200-item batch
that another selection could not complete. StoreBrowse's GET boundary depended on
encoding and total URL length. No stable public maximum or throughput guarantee
was found. Do not hard-code 196, 200, or 305 as an upstream contract.

Proposed operational default: 100 games per batch, separately configurable by
endpoint, with a measured encoded-URL budget and strict completeness checks.
Start with a conservative 6,000-byte full-URL budget for both endpoints; this is
our guardrail, not a discovered server limit. Split before sending when either
budget is exceeded. Keep the default at or below validated sizes until wider QA.
Sustained throughput, timeout recovery, and concurrent operation remain unverified.
These are compatibility probes, not production benchmarks or catalog guarantees.

## Multiple countries in one request

No supported multi-country request was found in either investigated interface.
Use one request per country per batch of games.

| Probe | Observed result |
| --- | --- |
| appdetails with `cc=pl,us` | One price per game, in PLN; no country-indexed response. Treat the malformed country's behavior as fallback, not support. |
| appdetails with repeated `cc=pl&cc=us` | One price per game, in USD; no multi-country result. |
| StoreBrowse context with `country_code: ["PL", "US"]` | HTTP 200 with an empty response object. |
| StoreBrowse context with `country_code: "PL,US"` | HTTP 200 with an empty response object. |

The StoreBrowse protocol has a repeated list of item IDs but a single request
context with a scalar country code. Neither the context nor individual item IDs
provides a supported collection of countries. This and the live probes establish
no usable multi-country path here, not proof that no other Steam service exists.
Different `cc` values select storefront offers; they do not establish independent
European/American server quotas. Retain shared pacing/backoff across providers.

## appdetails: separate metadata and prices

Price batching succeeded for 3, 7, and 25 app IDs, using:

```text
GET https://store.steampowered.com/api/appdetails
    ?appids=413150,1145360,1091500&cc=pl&l=english&filters=price_overview
```

Each priced item supplies its currency, initial/final integer amounts, and discount
percentage. This matches the existing price representation. Three-ID requests
using `basic,developers,publishers`, or adding those fields to `price_overview`,
returned HTTP 400. A one-ID metadata request succeeded. Therefore the current
combined filter cannot simply be reused with comma-separated app IDs.

Two appdetails-only options are feasible:

- Fetch metadata individually once per game, then batch prices per country.
- Fetch metadata plus baseline price individually once per game, then batch only
  alternative-country prices. This saves a baseline batch when that price is fresh.

Metadata must be cached independently to avoid paying the per-game cost again
on every price refresh. The `basic` filter also returns substantial descriptive
HTML/text: the Hades metadata response alone was about 10.7 KB. Parse only needed
fields and never forward/execute upstream HTML.

A price-only response cannot establish free-product status: Dota 2 returned
`{"success":true,"data":[]}`. This exact empty-array shape needs intentional
handling; arbitrary non-object data must still fail validation. Missing prices
must not be treated as proof that a game is free. Join validated metadata or use
an individual lookup when classification is unresolved.

## StoreBrowse.GetItems

The following anonymous request succeeded; a Web API key is not required for the
observed use. It is not a promise of future anonymous availability.

```json
{
  "ids": [{"appid": 413150}, {"appid": 1145360}],
  "context": {"country_code": "PL", "language": "english"},
  "data_request": {
    "include_basic_info": true,
    "include_best_purchase_option": false
  }
}
```

Send this as URL-encoded `input_json` to:

```text
https://api.steampowered.com/IStoreBrowseService/GetItems/v1/
```

Observed modes:

- Metadata only: the flags above returned names, type, free status when true, and
  developer/publisher entries without purchase options. A 25-item batch succeeded
  (about 19.9 KB in PL).
- Metadata plus price: set `include_best_purchase_option` to true. All five
  25-item batches succeeded (about 28-30 KB each).
- Price without basic info: set `include_basic_info` false and best-option true.
  This succeeded for three items; common fields such as name still appeared.
- All options: `include_all_purchase_options: true` exposed package/bundle choices
  for Children of Morta, Cyberpunk 2077, and the Hades soundtrack in PL and US.

Match records by requested `id` and item type, never array position or `appid`
alone. Invalid IDs returned `success:15`, `visible:false`, and `appid:0` while
preserving `id`. Dying Light in Germany also returned success 15, but retained its
name/appid and `unvailable_for_country_restriction:true` (the spelling is upstream).
Do not classify all non-success records as the same kind of unavailability.

Hades Original Soundtrack returned a developer but no publisher list. A singleton
appdetails check also omitted publishers. Missing credits are therefore not by
themselves a reason for endless retries. Distinguish a completed metadata response
with unavailable credits from metadata that has not been obtained.

### Why an exclusive StoreBrowse implementation is not equivalent today

Of 119 paid item-country pairs, 114 had the same final price as appdetails. All five
final-price differences were Children of Morta: StoreBrowse selected a cheaper
Complete Edition bundle, while appdetails supplied the standalone game offer.
For Poland the observed figures were:

| Item/field | appdetails | StoreBrowse best purchase option |
| --- | --- | --- |
| Children of Morta offer | Standalone game, package 53348 | Complete Edition bundle 22978 |
| Children of Morta final price | PLN 79.99 | PLN 19.99 |
| Cyberpunk 2077 final price | PLN 59.70 | PLN 59.70 |
| Cyberpunk 2077 base/original price | PLN 199.00 | PLN 59.70 |
| Cyberpunk 2077 discount percent | 70 | 0 |

StoreBrowse's Polish Cyberpunk response included
`hide_discount_pct_for_compliance:true` and
`price_cannot_be_displayed_as_discount:true`, along with an active discount.
The same base/discount difference occurred for Cult of the Lamb, Enter the
Gungeon, and Phantom Liberty in PL. These fields have different presentation
semantics; a zero here cannot safely mean no sale in the existing app.
Do not reconstruct base prices by summing discount components without a verified
contract, or overwrite appdetails discount metadata with these values.

Requesting all purchase options exposed Children of Morta's standalone package
at the appdetails price, but does not establish a universal rule to select the
same package for every game/edition/region. It also did not resolve Cyberpunk's
Polish base-price/discount difference.

Additional compatibility issues:

- Observed purchase options did not include an explicit currency code. Formatted
  price text and the requested country are weaker validation than appdetails'
  explicit returned currency. Do not parse symbols or silently label a fallback
  currency as the requested one.
- Int64 amounts arrive as JSON strings. Regular-price responses often omit
  original-price/discount fields; successful protobuf defaults need an explicit
  normalization contract rather than accepting arbitrary absent data as zero.
- Bundle, package, recurring-payment, edition, and temporary-free offers need
  explicit selection rules. A cheaper bundle can be useful future functionality,
  but substituting it changes the comparison's product definition.

StoreBrowse-only retrieval is technically feasible for its own offer model.
It is not a drop-in replacement preserving today's price and discount behavior.
A StoreBrowse-first pricing path with appdetails fallbacks is another hybrid,
but needs a broader equivalence study and still lacks explicit currency validation.

## Clarified product requirements and open offer choice

The user selected one discount definition: reduction from the regular base price
of the same offer, `(base - final) / base * 100`, independent of a 30-day-low
reference. If the base is missing or zero, the percentage is unavailable. Preserve
raw source amounts and reported percentage; do not reinterpret a presentation-
compliance zero as proof of no discount. Rounding policy must distinguish a
computed exact ratio from Steam's reported rounded percentage.

The Polish Cyberpunk store page showed Normally PLN 199.00, 30-Day Low PLN 59.70,
and Now PLN 59.70. Its appdetails 70% reduction matches the selected regular-base
metric. Valve's discounting FAQ acknowledges regional display differences while
retaining the discounted transaction price. These observations explain the data
semantics without claiming a published cross-API field-equivalence contract.

Offer selection is a separate unresolved decision. StoreBrowse's best option can
be a bundle, as observed for Children of Morta; this does not establish that every
returned option is the absolute cheapest eligible offer for every user. A logged-
out query cannot account for personal ownership and bundle eligibility.
The same store page showed both PLN 19.99 for the Complete Edition bundle and
PLN 79.99 for the individual game. Neither observation was inherently incorrect.

Options for later product work:

- Keep the current appdetails/default-offer comparison. This preserves behavior,
  but is not a guarantee of the lowest cost to obtain the game. price_overview
  itself does not identify the selected package, so strict identical-edition
  comparisons across countries would need additional offer identity validation.
- Compare lowest qualifying acquisition offers per country. Record offer ID,
  type, contents, purchase conditions, and base/final price together; account for
  countries choosing different bundles. Never attach the standalone game's base
  price or discount to a bundle's final price.
- Keep the existing comparison and separately identify a cheaper qualifying offer.
  This is a possible future recommendation, not an approved UI change or an extra
  data request in the current backend plan.

A bundle percentage may be an additional reduction on already discounted
components, not a reduction against their regular-price sum. For example, regular
components totaling 140, currently totaling 100, with an extra 20% bundle discount
cost 80: 20% below the current subtotal but 42.86% below the regular component sum.
Neither is automatically the discount from the bundle's own regular base price.
The comparison must name its reference and preserve matched offer data.

## Request-count comparison and additional storefronts

Let N be games needing metadata and prices, R be requested countries, and
B = ceil(N / 100) for the proposed default. With differently sized metadata and
price batches, use ceil(N / M) + R * ceil(N / P), where M and P are their limits.
These are full-coverage counts before URL-driven splitting, discovery, exchange
rates, retries, unavailable products, recovery fallbacks, and fresh caches.

| Scenario | Current N * R | Hybrid metadata + prices | Fresh metadata, stale prices |
| --- | ---: | ---: | ---: |
| 1 game, 2 countries | 2 | 3 | 2 |
| 100 games, 2 countries | 200 | 3 | 2 |
| 100 games, 3 countries | 300 | 4 | 3 |
| 100 games, 5 countries | 500 | 6 | 5 |
| 1,000 games, 5 countries | 5,000 | 60 | 50 |
| 1,000 games, 10 countries | 10,000 | 110 | 100 |

Ten countries is a scaling illustration, not implemented support. One game uses
exactly the same pipeline; the extra metadata request is accepted in exchange for
simpler implementation and verification. There is no list-size strategy switch.

### Optimization ceiling and diminishing returns

For 100 games across five countries, batch sizes of 25, 50, and 100 require
24, 12, and 6 hybrid requests respectively. Increasing beyond 100 cannot reduce
that six-request cold-data floor for this list: one metadata batch plus one
price batch per country. With fresh metadata the floor is five price requests;
with all observations fresh the price/metadata network cost is zero. Discovery
or stale exchange rates may still require their own requests.

For 1,000 games/five countries, a hypothetical reliable batch size of 200 would
reduce 60 hybrid requests to 30. A metadata-only increase from 100 to 300, while
keeping price batches at 100, would reduce 60 to 54. Neither is the proposed
default: appdetails near-200 reliability is unproven and long StoreBrowse URLs
already encounter transport limits. Greater batches improve request counts but
increase payload/parse work, failure scope, cancellation latency, and the delay
before any completed batch can be displayed.

At the current 1.5-second gate, K request starts need at least (K-1)*1.5 seconds
of spacing. Six starts imply 7.5 seconds of spacing versus 748.5 for 500 starts.
This is NOT an end-to-end latency estimate: request durations, metadata/name
prefetch, retries, caches, and result polling matter; the current worker can stop
early on missing prices. An approximately 83-fold request-count reduction here
must not be advertised as an 83-fold speedup.

The remaining performance opportunities, in priority order, are cache reuse,
batched work and partial-result delivery, then measured bounded overlap of slow
requests. Concurrency at unchanged pacing can hide network waits but cannot
eliminate the request-start spacing. Faster pacing, other geographic servers,
and unverified multi-country endpoints are not assumed optimizations.

Measure time to first usable row and total completion separately before deciding
whether smaller initial windows help. Do not add a special single-game path or
an automatic batch-growth algorithm for speculative gains. As storefront count
increases, price work remains linear in countries because each batch has one
country context; no supported request covering all countries was found.

More countries add a price batch per window, not another metadata fetch per game.
Memory scales with N * R small observations. A server-side collection keyed by
(app_id, country), joined with a metadata cache, avoids fixed three-column
assumptions. Keep original observations independent of the selected baseline.

Country and currency are separate identities: adding another EUR country must
not reuse Germany's regional price merely because both use EUR. Exchange-rate
quotes can be shared by currency. Future currencies also require verified minor
unit handling and supported rate coverage; do not assume the current five-country
mapping or numerical scaling covers every Steam market.

## Backend implementation shape

1. Plan missing/stale data by game and country using the existing price cache.
   Fetch no fresh observations again solely because another row or catalog uses
   them. Retain deterministic requested game and country order.
2. Fetch missing metadata in bounded StoreBrowse batches in a supported context.
   Preserve the origin country/language and retrieval time. A country-restricted
   response must not poison global metadata; retry a suitable requested country
   or use a bounded singleton fallback when needed. Metadata reuse is not proof
   of regional product availability.
3. Fetch price-only appdetails batches per requested country. Validate each entry,
   currency, amount, and metadata independently. Keep successful observations even
   if another item or country fails; the existing comparison renderer can retain
   its current all-required-countries behavior for now.
4. Join metadata and prices into the current result contract. Use independent
   metadata completeness/version/timestamps so fresh price refreshes do not erase
   credits or falsely reset metadata age, and missing credits do not refetch forever.
5. Keep failures local to their item/country where possible. Empty or omitted
   records are not evidence that every item is unavailable. Bound retries and
   singleton fallback. Do not fan out a throttled batch into many singleton calls;
   respect shared backoff. Network permission denial still stops work immediately.
6. Check cancellation before each batch/fallback and between progress emissions.
   Preserve price TTLs, sale TTLs, stale labels, retry behavior, and privacy rules.
   Record HTTP request counts separately from observations served: one batch is
   one network request, not 25. Review existing per-row/CSV counters accordingly.
7. Keep the retrieval provider independent of ComparisonConfig's current two-
   alternative limit. Later lifting that limit needs separate API/UI validation,
   layout, statistics, and export checks, not another retrieval rewrite.

The current SQLite price primary key (app_id, region) already scales across
countries. Its metadata currently lives in each regional row, so an independently
versioned metadata store and a compatible migration need design. Comparison
arithmetic already iterates alternatives, but configuration and web validation
explicitly cap them at two. This investigation does not change those limits.

## Verification required before integration

- Batched versus singleton equivalence for regular/sale prices, currency mismatch,
  free games, paid DLC/soundtracks, invalid IDs, and region restrictions.
- Missing, reordered, duplicated, malformed, and partially returned batch entries;
  repeated/empty credit lists and region-dependent metadata visibility.
- Cache migration and metadata freshness; no false refresh of another observation's
  timestamp, no credit erasure, and honest partial-result provenance.
- Stable loading order, Name prefetch, cancellation, retry, single-worker locking,
  and no extra requests for fresh cached data or merely viewing results.
- Shared throttling/backoff and bounded fallback under 400/429/5xx/transport errors;
  distinguish deterministic unsupported queries from transient failures.
- Request-count accounting and existing CSV behavior with a batched backend.
- Measure first-result latency and total completion time on representative lists,
  using three and five storefronts and a test configuration with more storefronts.
  Validate further real countries individually before advertising support.

No new automated application tests were added or run during this research;
application behavior was not changed. The live checks do not replace regression
coverage for the eventual implementation.

## Sources and reproducibility

- Direct live observations: the endpoint/request examples above and ignored QA
  responses dated 2026-10-18 locally. Public prices are snapshots, not guarantees.
- [SteamDatabase's extracted StoreBrowse protocol definitions](https://github.com/SteamDatabase/Protobufs/blob/master/steam/steammessages_storebrowse.steamclient.proto):
  request shape, metadata/option flags, and purchase-option fields. This is an
  extracted protocol reference, not a Valve stability guarantee.
- [Valve bundle documentation](https://partner.steamgames.com/doc/store/application/bundles):
  bundle types, additional discounts, and ownership-dependent eligibility.
- [Valve discounting FAQ](https://partner.steamgames.com/doc/marketing/discounts):
  regional presentation differences despite an unchanged discounted price.
- [Steam Web API overview](https://partner.steamgames.com/doc/webapi_overview):
  public and partner interfaces. Partner access is not a selected solution.

The anonymous GetSupportedAPIList probe did not enumerate StoreBrowse in this
session despite successful direct GetItems calls. Do not use that list as a
complete capability check or infer that GetItems has a documented service SLA.
