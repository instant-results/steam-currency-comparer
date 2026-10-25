# Wishlist Price and Discount loading-order research

Verified: 2026-10-24 (Europe/Warsaw), against version 0.10.0.
Research describes the 0.10.0 baseline. Version 0.11.0 implements the selected
behavior on 2026-10-25; the chosen behavior is recorded below.
See the [sorted-wishlist integration brief](STEAM_SORTED_WISHLIST_API.md) for
the earlier work on Name, Top Selling, Release Date and Review Score.

## Finding

Steam can return its Price and Discount order before this application fetches
game details or regional prices. Its current public wishlist frontend maps
Price to `sort_order: 2` and Discount to `sort_order: 3`, then calls
`IWishlistService/GetWishlistSortedFiltered/v1/`.

Live anonymous requests with `data_request: {}` and `page_size: 0` returned
ordered lightweight records with no `store_item` objects. Their complete
returned sequences matched requests with detailed data for five records, a
later five-record window, and every returned record in the Polish sample.
Fetching all details was part of validation, not a prerequisite for obtaining
the order.

Two qualifications prevent treating this as a direct replacement for the
current wishlist retrieval:

- Steam's Price order matched its selected purchase offer, including bundles.
  It did not always match the default game prices used by this application.
- The sorted endpoint returned a country-dependent subset of the basic wishlist,
  even with `filters: {}`. Missing products must not silently disappear from
  this application's selection.

## Method and evidence

One user-designated public wishlist was checked anonymously in PL, US and DE.
Requests used verified HTTPS and the project's HTTP client, sequentially paced
at least 1.5 seconds apart within each probe sequence. No sign-in, Web API key,
share token or authenticated cookies were supplied. No account or wishlist
mutation was performed.

The basic `GetWishlist` response was compared before and after the probes;
its membership stayed unchanged. Validation compared full sequences, unique
IDs, enrichment positions, offer prices, discount fields and missing records.
Eight price-only appdetails batches, each at most 100 IDs, checked the Polish
default-offer interpretation. Separate StoreBrowse batches inspected omitted
entries and products without offers. All findings below describe this sample,
not an upstream compatibility or latency guarantee.

Profile identifiers, game IDs/titles/prices, raw responses and temporary scripts
remain in ignored local QA storage under `.steam-price-polisher/qa/sorted-wishlist/`.
Only aggregate findings belong in tracked documentation. Do not upload that
directory or convert the real wishlist into regression fixtures.

### Ordered list and detail windows

| Request in PL | Returned records | Detailed records | Sequence compared with full-detail request |
| --- | ---: | ---: | --- |
| Price, empty data request, page size 0 | 749 | 0 | Identical |
| Discount, empty data request, page size 0 | 749 | 0 | Identical |
| Price / Discount, page size 5, start 0 | 749 each | 5 each | Identical |
| Price / Discount, page size 5, start 100 | 749 each | 5 each | Identical |
| Price / Discount, page size 1000, start 0 | 749 each | 749 each | Reference |

For the offset requests, only zero-based positions 100 through 104 contained
`store_item`. Thus `page_size` limited enrichment in these responses, rather
than paginating the outer item list. A successful request for 1000 details is
not evidence of a universal maximum; normal loading need not request them all.

A minimal observed request is:

```json
{
  "steamid": "<PUBLIC_TEST_STEAMID64>",
  "context": {"language": "english", "country_code": "PL"},
  "data_request": {},
  "sort_order": 2,
  "filters": {},
  "start_index": 0,
  "page_size": 0
}
```

Send it as URL-encoded JSON in `input_json`; use `3` for Discount. The API
metadata still describes `share_token` as non-optional, but these public-list
requests succeeded without one. That observation does not establish access to
private or shared-token-only lists.

### Price

In all three storefronts the returned sequence contained free products first,
then purchasable offers in ascending `best_purchase_option.final_price_in_cents`,
then non-free products without an offer. There were no adjacent price-order
inversions among the priced offers.

| Storefront | Returned | Priced offers | Free products | Other products without offers |
| --- | ---: | ---: | ---: | ---: |
| PL | 749 | 629 | 60 | 60 |
| US | 749 | 639 | 60 | 50 |
| DE | 676 | 595 | 49 | 32 |

Among the 60 Polish non-free products without offers, a follow-up metadata
request marked 20 as coming soon. All 60 occupied the tail of Price order.
This does not establish a rule for all preorders, temporary free promotions,
subscriptions or products with unusual purchase eligibility.

All 629 Polish priced entries also had default prices from appdetails. Of these,
618 matched the selected offer price; 11 selected offers were cheaper bundles.
Reading the returned sequence against default game prices produced eight
adjacent price-order inversions. Therefore a Steam-ordered list can visibly
break ascending order in this application's default-price column.

### Discount

US and DE offered descending `best_purchase_option.discount_pct` among priced
entries, treating an omitted field as protobuf zero for this validation.
There were no adjacent inversions in either storefront. Priced products,
including those with zero discount, preceded the mixed tail of free products
and other products without offers.

PL requires more care. Of its priced offers, 68 had
`hide_discount_pct_for_compliance` and zero/omitted headline percentages despite
active discount data. Simply sorting the exposed headline field did not
reproduce the response: that metric had ten adjacent inversions. For the 618
non-bundle offers, appdetails discount percentages were descending without
inversions. The whole default-price sequence had four discount inversions
when bundle-selected entries were included.

This supports using Steam's returned order as authoritative for a Steam-style
Discount option. It does not establish a universal formula for Steam's internal
discount key, especially for bundles and compliance presentation. Do not rebuild
that key from the displayed percentage, infer zero discount from a hidden badge,
or substitute bundle component savings for the application's regular-price
discount calculation.

### Storefront context and ties

PL versus US and PL versus DE produced different relative orders for common
products under both Price and Discount. The selected country therefore matters;
the baseline storefront is a coherent proposed choice for this application.
There is no evidence here for ordering by the cheapest price across all selected
comparison countries without retrieving those countries' observations first.

The request schema exposes a sort enum but no separate direction field. The
observed defaults are ascending Price and descending Discount. No reverse-sort
API option was verified.

The repeated PL sequences were identical across detail-window requests, but
ties did not consistently follow simple name, App ID, priority or date-added
ordering. Preserve server order within ties; no lasting tie-break guarantee was
established. Prices, sales and upstream indexes can change between requests.

### Missing membership is independent of the selected sort

The basic wishlist contained 759 distinct entries in both checks. Price and
Discount each returned 749 in PL/US and 676 in DE. Price and Discount membership
was identical within each country. Additional Your Rank requests to the sorted
endpoint returned the same membership as Price in PL and DE.

Separate StoreBrowse checks found:

- The ten entries absent in PL had `success: 15`, `visible: false`, and no
  country-restriction flag. None had a Polish appdetails price. These fields
  do not establish the exact reason each product was unavailable.
- DE omitted those same ten entries plus 73 explicitly flagged
  `unvailable_for_country_restriction` (the upstream spelling).

Consequently, an empty filter object does not mean every basic wishlist entry
will be returned. The inspected wishlist filter schema contains platform, type,
price, discount, tag, content-descriptor, category and demo filters; no explicit
include-unavailable switch was found there. No request workaround for complete
membership was established.

This corrects the earlier brief's assumption that a complete sorted response
necessarily equals the entire basic wishlist. Any adoption of this endpoint,
including the earlier proposed sorts, needs a membership policy.

## Options for the application

### A. Follow Steam's loading order

Obtain a lightweight sorted sequence for the chosen baseline, then process
regional comparisons in that order. Retain the basic wishlist call to establish
membership. A proposed reconciliation is to keep the basic response as the
selection, order its intersection with the sorted response by Steam, and append
omitted entries in their original basic-list order with explicit unavailable/
unranked handling. Validate unexpected additions and inconsistent snapshots;
do not silently import or drop IDs between the two responses.

This would require two wishlist discovery calls for these modes, before ordinary
comparison work. It avoids a full baseline-price prefetch, but its offer choices
can differ from the default-price columns. Labels/help must explain that this is
Steam's order for the baseline storefront. Appending omitted entries is an
application policy, not a claim to reproduce Steam's entire visible page.

### B. Order by the application's default baseline prices

Fetch/reuse all needed baseline prices and classification metadata first, sort
by the same default final price or discount used in the table, then perform the
remaining regional comparisons in that order. This needs data for the whole
baseline selection before emitting a globally ordered first row, but does not
need prices for every alternative storefront first. Cache reuse limits duplicate
work. Free, missing, zero and unknown values need an explicit stable policy.

This gives consistent displayed-value ordering and works for manual selections
too. It adds startup work for a cold wishlist; no latency benchmark of this
approach was conducted. Re-sorting only the first fetched chunk would not provide
correct global loading order.

### Implemented choice (0.11.0, 2026-10-25)

Price and Discount use option B: fetch all baseline observations before publishing
rows, then reuse the same snapshot while comparing regional windows. The existing
checkbox exposes two primary-offer choices. Game primary uses the standalone
price; best-offer primary uses Steam's cheaper qualifying package/bundle, falling
back to the game per country. No exhaustive bundle enumeration is added.

A game and its alternative occupy one indivisible paired row. Primary prices
control filters, sorting, comparisons and statistics. Removal/Undo and manual
addition operate on the underlying game. Effective discounts use the regular game
price against the cheaper acquisition price, with a distinct badge. Raw offer
percentages remain separate in CSV; they never substitute for effective savings.

Top Selling, Release Date and Review Score use the minimal sorted endpoint in the
baseline country. Reconcile against the complete basic wishlist, appending omitted
entries in basic-response order without a ranking badge. On ordering failure,
fail explicitly rather than changing sort. Manual selections/examples retain
selection order for those Steam-only modes; additions append. Price/Discount
additions reorder the combined selection. Currency updates preserve emitted order
while the source job survives; an expired source is reconstructed normally. Retry
uses the saved order and offer basis, with fresh ordering/observations as needed.
Changing the display primary later does not change the original loading sequence.

## Validation scope

Use synthetic fixtures for lightweight and enriched responses, offset windows,
country-dependent omissions, missing/reordered metadata, duplicate IDs, free and
unpriced entries, bundle/default-price differences, hidden discount percentages,
stable tie preservation, and failures without misleading fallback. Verify order
through progress emission, reload, retry, removals, manual additions and currency
updates. Keep feature and test commits separate when committing is authorized.

The live sample covered one public wishlist, three storefronts, one time window,
and anonymous access. It did not verify all 37 countries, authenticated account
preferences, shared tokens, lists above 1000 entries, a maximum enrichment window,
long-term tie stability, or an identical rendering of a signed-in Steam wishlist.
A 2026-10-25 follow-up exercised Top Selling, Release Date and Review Score
through the production reconciliation path in PL and DE: all six calls succeeded,
returned changed sequences and retained all 759 basic-list entries. This validates
current response compatibility and membership, not Steam's undisclosed ranking
formula or behavior across every country.

## Primary sources and reproduction

- [Steam API metadata](https://api.steampowered.com/ISteamWebAPIUtil/GetSupportedAPIList/v1/):
  current wishlist method parameters; retrieved directly with verified HTTPS.
- [Current Steam wishlist page](https://store.steampowered.com/wishlist/):
  source of the public frontend asset URLs on the research date.
- [Wishlist frontend module](https://cdn.akamai.steamstatic.com/store/ssr/Cd8kGth4.js):
  enum mapping and server-side sorted-list call, followed by extraction of the
  returned ordered records. SHA-256 of the saved UTF-8 source:
  `b3c88fc918030b538790a3f87f6cd8226dd75bac1d4dfb4397b13c2b0e1c06ed`.
- [Wishlist message schema](https://cdn.akamai.steamstatic.com/store/ssr/wm7CwcOP.js):
  request defaults, filter fields and response item shape. SHA-256:
  `0e9e67aad40a1f364764777e3832fcb93951983bd34b8838fc1ea9aaa07128ab`.
- [Store context helper](https://cdn.akamai.steamstatic.com/store/ssr/B0AbdXTx.js):
  copies country and language into public requests. SHA-256:
  `24623e1785f5752b0c8793168315613876d05554338c48c034ea37ee90c83f27`.
- [Valve bundle documentation](https://partner.steamgames.com/doc/store/application/bundles):
  bundle discounts and ownership-dependent purchase behavior. Anonymous offer
  observations are not a personalized checkout quote.

Hashed frontend URLs can change. Rediscover them from the current public page
rather than relying on the older `applications/store/main.js` URL. The aggregate
observations above come from direct API requests, not a documented promise of
Steam's internal sorting algorithm. Reproduce with a designated public wishlist,
minimal request windows and normal pacing; keep identity and contents private.
