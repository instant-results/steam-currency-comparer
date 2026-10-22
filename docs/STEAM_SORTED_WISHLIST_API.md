# Steam sorted wishlist API — implementation handoff

Research verified: 2026-09-12. This is an implementation brief, not a claim
that Valve guarantees every observed response detail indefinitely.
Implementation status checked against the repository on 2026-10-02: still not
integrated. The live API observations remain dated 2026-09-12 and were not
re-probed during the documentation refresh; revalidate before implementation.

## Objective

Evaluate Steam's richer wishlist-page service as the source of loading order and
catalog metadata for Steam Currency Comparer. The immediate opportunity is to
match Steam's **Release Date**, **Top Selling**, and **Review Score** sorts without
first fetching regional prices for every game.

No integration described here has been started. The application still uses
`IWishlistService/GetWishlist/v1` as its primary wishlist source.

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
or share token. It returned the complete lightweight wishlist in the requested
server-side order. Only the range selected by `start_index` and `page_size` was
decorated with a nested `store_item`. This matches Steam's description that Store
Browse data is filled into that range; `page_size` did **not** truncate the
top-level item list in the observed response.

The service can therefore provide Steam's ordering for all items while limiting
rich metadata to a manageable window. Its detailed contract is not formally
documented, so parsing must be defensive and retain the current `GetWishlist`
path as a fallback.

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
- `context.country_code` affects Store Browse data and may affect
  region-sensitive sorting such as Top Selling. Deliberately choose whether it
  follows the selected baseline storefront or another product rule.
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

This working mapping matches Steam's UI order and live response behavior. Numeric
values are observed protocol details and need contract tests because the public
API metadata exposes only an enum type, not its labels.

| Value | Steam label | Evidence and handling |
|---:|---|---|
| `0` | Your Rank | Default; observed priorities ascending. |
| `1` | Name | Observed names ascending. |
| `2` | Price | Outside the current request; requires storefront semantics. |
| `3` | Discount | Outside the current request; dynamic. |
| `4` | Date Added | Observed timestamps descending. |
| `5` | Top Selling | Server-defined and dynamic; no numeric rank was returned. |
| `6` | Release Date | Server-defined handling for past, upcoming, and unknown dates. |
| `7` | Review Score | Observed review-score ordering; not just percent positive. |

Expose named internal constants or an enum. Do not scatter these integers across
the web, analysis, and access layers.

## Recommended integration

Prefer one retrieval abstraction with two implementations:

1. Add `SteamClient.get_wishlist_sorted_filtered(...)` beside `get_wishlist`.
2. Map product order names to a typed Steam sort enum in `steam_access.py`.
3. Request the complete server-side order and enrich only the first processing
   window. Preserve every item when `store_item` is absent.
4. Process items in response order. Fetch later metadata windows only if the UI
   needs release/review fields before regional `appdetails` provides a name.
5. Fall back to `GetWishlist/v1` only when doing so preserves the requested
   semantics. Retain existing TLS, network-denial, malformed-response, and retry
   classifications.
6. Keep local sorting as fallback for Your Rank, Date Added, and Name when enough
   metadata exists. For Top Selling, Release Date, and Review Score, expose a
   clear unsupported/failure state if authoritative ordering is unavailable;
   silently substituting another order would be misleading.

Replacing the primary endpoint for every order would match Steam most closely
but introduces a larger undocumented response surface. A staged implementation
is safer: add and validate the client method, use it for one sort, then expand.

## Files likely to change

- `steam_price_polisher/steam_access.py`: request construction, enum mapping,
  defensive parsing, and fallback policy.
- `steam_price_polisher/models.py`: optional metadata only if retained or
  displayed. Server-provided sequence alone needs no new fields.
- `steam_price_polisher/analysis.py`: accept authoritative response order and
  remove alphabetical baseline prefetch when Name comes from this service.
- `steam_price_polisher/web_app.py`: validate product order values and expose
  precise failure messages.
- `web/index.html` and `web/app.js`: add Release Date, Top Selling, and Review
  Score options and persist them with jobs.
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
- Top Selling, Release Date, and Review Score never silently fall back to a
  semantically different local order.
- Network denial, TLS failure, rate limiting, invalid JSON, and fallback remain
  distinguishable and sanitized.
- A fixture proves `page_size` limits enrichment rather than deleting lightweight
  wishlist items.
- Any optional live contract test is manually invoked, uses a designated public
  test profile, records no wishlist contents, and stays out of normal unit tests.

## Acceptance criteria

- The requested order dictates the first and every subsequent game processed.
- UI labels match Steam: Your Rank, Name, Date Added, Top Selling, Release Date,
  and Review Score.
- A public wishlist needs no Steam sign-in, cookie, or user Web API key.
- Top Selling follows a documented country/storefront rule.
- Missing rich metadata neither loses games nor exposes private data.
- Regional pricing, pacing, caching, cancellation, and partial-result handling
  remain unchanged unless explicitly redesigned and tested.
- Documentation and fixtures distinguish observed behavior from guarantees.

## Open decisions

1. Should Top Selling use the baseline storefront's country? This is coherent,
   but changing the baseline could change load order.
2. Should release/review metadata be displayed or used only for ordering?
   Displaying it expands model, API, rendering, and CSV scope.
3. Should `GetWishlistSortedFiltered` replace the primary call or only support
   sorts the lightweight endpoint cannot reproduce?
4. How should an absent share token interact with future shared-wishlist URLs?
   Treat any token as a secret capability.
5. Should the historical `/wishlistdata/` fallback be removed after the new
   service is proven, or retained behind a contract check?

## Revalidation procedure

Before implementation, query official API metadata again and run a schema-only
probe. Do not print or commit app IDs, titles, profile identifiers, share tokens,
or prices from a real user's wishlist.

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
