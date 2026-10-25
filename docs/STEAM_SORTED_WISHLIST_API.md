# Steam sorted wishlist API — implementation handoff

Original research: 2026-09-12; follow-up research: 2026-10-24. Integration added
2026-10-25 in version 0.11.0. Observed API details are not Valve guarantees.
See [Price and Discount findings](STEAM_WISHLIST_PRICE_DISCOUNT.md).

## Implemented scope

Basic `GetWishlist` remains the membership source. `SteamClient.get_wishlist_order`
requests lightweight sorted records for Top Selling (5), Release Date (6) and
Review Score (7), using the baseline country, empty filters/data request and
`page_size: 0`. It keeps matching basic entries in Steam's sequence, then appends
missing basic entries in original order. No ranking-status badge is displayed.
Duplicates, malformed IDs and invalid envelopes fail explicitly; failure never
silently substitutes a different sort. Rich records are not needed for ordering.

Price and Discount use a complete baseline prefetch, based on the selected primary
game or cheaper Steam offer. Name retains metadata prefetch; Your Rank and Date
Added retain basic metadata sorting. Currency updates preserve emitted order;
manual lists/examples keep selection order for Steam-only modes. Manual additions
append for non-price orders. Changing primary display uses already loaded data.

A 2026-10-25 live check of all three integrated Steam modes in PL and DE succeeded
and preserved all 759 basic entries after reconciliation. This is a response and
membership check, not independent verification of Steam's ranking algorithm.
The detailed observations below retain their original research dates.

## Executive summary

The current candidate is:

```text
GET https://api.steampowered.com/IWishlistService/GetWishlistSortedFiltered/v1/
```

Steam's `ISteamWebAPIUtil/GetSupportedAPIList/v1/` metadata describes it as
“Get a user's paginated wishlist applying various sorts and filters.” It accepts
a SteamID64, Store Browse context and data request, sort order, filters, start
index, page size, and wishlist share token.

A live anonymous request for a public wishlist succeeded without a Web API key
or share token. It returned a lightweight item list in the requested
server-side order. Only the range selected by `start_index` and `page_size` was
decorated with a nested `store_item`. This matches Steam's description that Store
Browse data is filled into that range; `page_size` did **not** truncate the
top-level item list in the observed response.

The service can therefore provide Steam's ordering for its returned selection
while limiting rich metadata to a manageable window. The 2026-10-24 checks found
that this selection can omit entries present in basic `GetWishlist`, even with
empty filters. Do not equate a complete sorted response with complete wishlist
membership. Retain the basic source for membership reconciliation; fallback must
also preserve the requested ordering semantics rather than silently substitute
another order.

## Relationship to the current implementation

Current code in `steam_price_polisher/steam_access.py` uses:

```text
GET https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid=...
```

That lightweight response supplies `appid`, `priority`, and `date_added`. The
application locally sorts those fields, and Name loading prefetches each game's
baseline storefront details to learn its name.

The same file contains a fallback for the historical route:

```text
GET https://store.steampowered.com/wishlist/{profiles|id}/{identifier}/wishlistdata/?p=...
```

On 2026-09-12, an anonymous request to that route redirected to the Steam store
homepage and returned HTML rather than JSON. Treat it as retired,
session-dependent, or otherwise unverified. Do not expand its parser or build new
sorting work on it until its current contract is independently reproduced. The
existing synthetic fixtures do not prove that the live route works.

## Request format

Steam accepts the structured request as URL-encoded JSON in `input_json`:

```json
{
  "steamid": "<PUBLIC_TEST_STEAMID64>",
  "context": {
    "language": "english",
    "country_code": "PL",
    "steam_realm": 1
  },
  "data_request": {
    "include_basic_info": true,
    "include_release": true,
    "include_reviews": true
  },
  "sort_order": 1,
  "filters": {},
  "start_index": 0,
  "page_size": 100
}
```

Important request behavior:

- Use `https://api.steampowered.com`, consistent with the current wishlist call.
- URL-encode the complete JSON value; do not construct nested query keys by hand.
- `context.country_code` affects Store Browse data, Price/Discount order and
  sorted-list membership; it may also affect Top Selling. Deliberately choose
  whether it follows the selected baseline storefront or another product rule.
- `data_request` controls which `store_item` sections are returned. Request only
  fields the feature uses.
- Steam's metadata says `share_token` determines visibility and effective
  filters. The public-wishlist probe succeeded without it. Supporting capability
  URLs is a separate security-sensitive feature; do not persist tokens
  incidentally.
- Defaults observed in Steam's public JavaScript protobuf definition are
  `start_index = 0` and `page_size = 100`.

Other Store Browse flags include assets, platforms, and purchase options. They
are unnecessary merely to obtain Name, Release Date, or Review Score. Regional
price comparison must continue using the project's region-explicit price path
unless a separately tested migration proves identical currency, availability,
sale, and cache behavior.

## Response shape

Steam's public JavaScript protobuf definition and a live JSON response agree on
this item envelope:

```json
{
  "response": {
    "items": [
      {
        "appid": 123,
        "priority": 0,
        "date_added": 1700000000,
        "store_item": {},
        "category_ids": []
      }
    ]
  }
}
```

`store_item` is absent outside the requested enrichment window and must be
treated as optional. With basic information, release information, and reviews
requested, observed store-item fields included:

- Identity/display: `item_type`, `id`, `appid`, `type`, `success`, `visible`,
  `name`, `store_url_path`, `store_url_slug`.
- Product state: `is_free`, `is_coming_soon`, `is_early_access`,
  `content_descriptorids`, `categories`, `related_items`.
- Requested sections: `basic_info`, `release`, `reviews`.
- Purchase data may appear as `best_purchase_option`; do not depend on it unless
  explicitly requested and validated for the chosen country and currency.

Observed review structure:

```text
store_item.reviews.summary_filtered.percent_positive
store_item.reviews.summary_filtered.review_count
store_item.reviews.summary_filtered.review_score
store_item.reviews.summary_filtered.review_score_label
```

`summary_language_specific` may also be present. Steam's Review Score ordering is
an opaque server-defined ranking; do not recreate it from `percent_positive`
alone.

Observed release structure:

```text
store_item.release.steam_release_date
store_item.release.original_steam_release_date
store_item.release.original_release_date
store_item.release.linux_release_date
store_item.release.is_coming_soon
store_item.release.is_early_access
store_item.release.custom_release_date_message
store_item.release.coming_soon_display
```

Release fields are optional and can represent exact dates, abridged dates,
“coming soon,” or custom text. Preserve Steam's returned Release Date order
instead of attempting a simple timestamp sort that mishandles these cases.

## Sort-order values

This working mapping matches Steam's UI order. The enum mapping was confirmed
in Steam's current wishlist frontend on 2026-10-24; Price and Discount received
fresh live checks. Modes 5/6/7 were also exercised on 2026-10-25 as described above.
Numeric values are observed protocol details and need contract tests because the
public API metadata exposes only an enum type, not its labels.

| Value | Steam label | Evidence and handling |
|---:|---|---|
| `0` | Your Rank | Default; observed priorities ascending. |
| `1` | Name | Observed names ascending. |
| `2` | Price | Researched 2026-10-24: ascending Steam-selected offer price; can differ from default game price. |
| `3` | Discount | Researched 2026-10-24: Steam discount order; hidden percentages and bundles prevent a simple universal reconstruction. |
| `4` | Date Added | Observed timestamps descending. |
| `5` | Top Selling | Server-defined and dynamic; no numeric rank was returned. |
| `6` | Release Date | Server-defined handling for past, upcoming, and unknown dates. |
| `7` | Review Score | Observed review-score ordering; not just percent positive. |

Expose named internal constants or an enum. Do not scatter these integers across
the web, analysis, and access layers.

## Original integration proposal (historical)

The proposal and checklists below record the original research plan. The
implemented 0.11.0 scope is described above; these are not outstanding feature
commitments or an alternative description of current behavior.

Prefer one retrieval abstraction with two implementations:

1. Add `SteamClient.get_wishlist_sorted_filtered(...)` beside `get_wishlist`.
2. Map product order names to a typed Steam sort enum in `steam_access.py`.
3. Request the server-side order and enrich only the first processing window,
   or request no details when only the sequence is needed. Reconcile membership
   with basic `GetWishlist` using an explicit omission policy. Preserve every
   returned item when `store_item` is absent.
4. Process items in response order. Fetch later metadata windows only if the UI
   needs release/review fields before regional `appdetails` provides a name.
5. Fall back to `GetWishlist/v1` only when doing so preserves the requested
   semantics. Retain existing TLS, network-denial, malformed-response, and retry
   classifications.
6. Keep local sorting as fallback for Your Rank, Date Added, and Name when enough
   metadata exists. For Top Selling, Release Date, Review Score, and Steam-style
   Price/Discount, expose a clear unsupported/failure state if authoritative
   ordering is unavailable. Local default-price sorting has different semantics
   and must not silently replace Steam order.

Replacing the primary endpoint for every order would match Steam most closely
but introduces a larger undocumented response surface. A staged implementation
is safer: add and validate the client method, use it for one sort, then expand.

## Original implementation checklist

- `steam_price_polisher/steam_access.py`: request construction, enum mapping,
  defensive parsing, and fallback policy.
- `steam_price_polisher/models.py`: optional metadata only if retained or
  displayed. Server-provided sequence alone needs no new fields.
- `steam_price_polisher/analysis.py`: accept authoritative response order and
  remove alphabetical baseline prefetch when Name comes from this service.
- `steam_price_polisher/web_app.py`: validate product order values and expose
  precise failure messages.
- `web/index.html` and `web/app.js`: add approved loading-order options and
  persist them with jobs. The original proposal covered Release Date, Top Selling
  and Review Score; Price/Discount labels depend on the offer-model decision.
- `tests/test_steam_access.py`, `tests/test_analysis.py`,
  `tests/test_web_app.py`, and `tests/test_web_render.cjs`: fixtures and behavior.

## Required tests

Keep feature and test changes in separate commits, per `AGENTS.md`.

- Request serialization includes the selected enum, country, requested data
  sections, start index, and page size.
- Parser accepts lightweight and enriched items in the same response.
- Missing or unsuccessful `store_item` does not discard the wishlist item.
- Malformed IDs, timestamps, review/release objects, and envelopes follow an
  explicit reject-or-ignore policy.
- Each product label maps to the expected Steam enum value.
- Response order survives deduplication, analysis, job snapshots, rendering,
  refresh, retry, and restoring original loading order via the header sort cycle.
- Name ordering no longer duplicates baseline price requests.
- Top Selling, Release Date, Review Score and Steam-style Price/Discount never
  silently fall back to a semantically different local order.
- Country-dependent omissions are reconciled with basic wishlist membership;
  incomplete responses never silently remove games from the comparison.
- Network denial, TLS failure, rate limiting, invalid JSON, and fallback remain
  distinguishable and sanitized.
- A fixture proves `page_size` limits enrichment rather than deleting lightweight
  wishlist items.
- Any optional live contract test is manually invoked, uses a designated public
  test profile, records no wishlist contents, and stays out of normal unit tests.

## Acceptance criteria

- The requested order dictates the first and every subsequent game processed.
- UI labels describe the approved semantics. Steam-parity candidates are Your
  Rank, Name, Price, Discount, Date Added, Top Selling, Release Date and Review
  Score; default-game Price/Discount sorting is a distinct option.
- A public wishlist needs no Steam sign-in, cookie, or user Web API key.
- Top Selling follows a documented country/storefront rule.
- Missing rich metadata neither loses games nor exposes private data.
- Regional pricing, pacing, caching, cancellation, and partial-result handling
  remain unchanged unless explicitly redesigned and tested.
- Documentation and fixtures distinguish observed behavior from guarantees.

## Remaining scope

No release/review metadata is exposed as new columns. Shared-wishlist tokens,
removal of the historical wishlist fallback and replacing basic membership with
the sorted endpoint remain outside this integration. Steam ordering can change
between fresh runs. Current Price/Discount labels promise app-selected primary
prices, not exact Steam-wishlist discount parity.

## Revalidation procedure

Before changing the integration contract, query official API metadata and run a schema-only
probe. Do not print or commit app IDs, titles, profile identifiers, share tokens,
or prices from a real user's wishlist.
Use the current request and membership checks in
[Price and Discount research](STEAM_WISHLIST_PRICE_DISCOUNT.md); the earlier
request below remains an example for enriched Name ordering.

PowerShell outline:

```powershell
$request = @{
    steamid = '<PUBLIC_TEST_STEAMID64>'
    context = @{ language = 'english'; country_code = 'PL'; steam_realm = 1 }
    data_request = @{
        include_basic_info = $true
        include_release = $true
        include_reviews = $true
    }
    sort_order = 1
    filters = @{}
    start_index = 0
    page_size = 5
} | ConvertTo-Json -Depth 8 -Compress

$encoded = [uri]::EscapeDataString($request)
$uri = 'https://api.steampowered.com/IWishlistService/' +
       'GetWishlistSortedFiltered/v1/?input_json=' + $encoded
$response = Invoke-RestMethod -Uri $uri
```

Inspect only field names and counts. Convert useful shapes into synthetic
fixtures; never commit a live response.

## Primary sources

- Steam live Web API metadata:
  <https://api.steampowered.com/ISteamWebAPIUtil/GetSupportedAPIList/v1/>
- Sorted wishlist method:
  <https://api.steampowered.com/IWishlistService/GetWishlistSortedFiltered/v1/>
- Current lightweight method:
  <https://api.steampowered.com/IWishlistService/GetWishlist/v1/>
- Steam public store JavaScript bundle inspected on 2026-09-12:
  <https://store.fastly.steamstatic.com/public/javascript/applications/store/main.js>
- Valve's wishlist metadata announcement:
  <https://store.steampowered.com/news/posts/?enddate=1536191359&feed=steam_blog>
- Valve's description of regional, revenue-based Top Sellers:
  <https://store.steampowered.com/news/posts/?enddate=1664816416&feed=steam_blog>
