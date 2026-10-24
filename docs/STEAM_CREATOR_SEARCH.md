# Steam creator search

Verified on 2026-10-03. This describes the implemented integration and its limits.

## Sources and prior work

- [Valve search announcement](https://store.steampowered.com/news/app/593110/view/3686801719533364952): creator suggestions in store search.
- [Steamworks creator homepages](https://partner.steamgames.com/doc/store/creator_homepage?l=english): products and multiple credited names can link to one community-group-backed homepage. Homepage membership and developer/publisher attribution are distinct.
- [Steam Web API overview](https://partner.steamgames.com/doc/webapi_overview): public and authenticated methods. The storefront contracts below are observed behavior, not a documented compatibility guarantee.
- [Augmented Steam implementation](https://github.com/IsThereAnyDeal/AugmentedSteam/blob/develop/src/js/Content/Features/Store/App/FReplaceDevPubLinks.ts): replaces homepage links with developer/publisher name-filtered product searches while retaining the homepage separately. Its ampersand special case warrants further compatibility checks for complex names.
- [First-hand developer report](https://www.reddit.com/r/gamedev/comments/139fgr3/): a homepage was missing from search until more products were linked. This is historical experience, not proof of a current minimum requirement.

## Live findings

The legacy `/search/suggest?term=supergiant&f=games` returned a matching game without a creator. `/curators/ajaxgetcurators/` ignored attempted `query` and `term` filters and returned an unrelated directory page. Neither is used for discovery.

Steam's current public storefront JavaScript calls `StoreQuery.SearchSuggestions` with `search_creators`. Direct anonymous HTTPS probes confirmed:

`https://api.steampowered.com/IStoreQueryService/SearchSuggestions/v1/`

The `input_json` parameter contains `search_term`, `max_results: 20`, `search_creators: true`, `context: {language: "english", country_code: "PL"}`, and `data_request: {include_basic_info: true}`. The response includes `metadata`, mixed `ids`, and `store_items`. Creator items use `item_type: 5`, an integer ID, `name`, and `store_url_path`. Only validated developer/publisher homepage items are returned; games and franchise pages are excluded. URL aliases do not establish an organization's role, so entries are labeled Creator homepage.

Probes found Supergiant Games (3584665), Devolver Digital (6638525), ConcernedApe (32938395), and poncle (44992428). A nonsense query returned zero-match metadata and omitted `store_items`. Suggestions are not an exhaustive directory or a promise of matching every spelling or studio.

`IStoreBrowseService/GetItems/v1/` accepts the same context/data request and `ids: [{creatorid: ID}]`. Before loading a dynamic homepage catalog, the worker resolves the ID again and requires a developer/publisher homepage. No API key, Steam login, or cookie was needed in these tests. Upstream behavior may change.

## Exact-name fallback

The Developers and Publishers tabs send a role with each search. Search checks the first product-search page for that role against suggested names and the entered exact name. Only nonempty regional catalogs are offered through Add. Steam homepages help discover names internally; they are not a third role or a selectable catalog source in the interface. This confirms Steam attribution rather than a company's legal identity. Spelling and Steam's own filter semantics affect coverage. Role checks use a bounded six-hour catalog cache; failed or stale checks produce a search error rather than unverified buttons.

`https://store.steampowered.com/search/results/` accepts `developer=NAME` or `publisher=NAME`, `start`, `count=12`, `cc`, `l=english`, `json=1`, `ignore_preferences=1`, and `infinite=1`. JSON contains `success`, `results_html`, `total_count`, and `start`, without `pagesize`. Empty searches returned `total_count: 0` and `start: -1`.

Live Valve checks on 2026-10-03 returned 25 rows despite `count=12`; `start=12` returned the first page again, while `start=25` advanced correctly. The parser bounds search pages to 50 rows and advances by at least the returned row count, including skipped entries.

The parser extracts individual app IDs and title text from `search_result_row` links. Packages and bundles are skipped while pagination advances through their slots. Steam HTML/scripts are never forwarded or executed. Totals can include these skipped entries and free products. Regional availability and Steam's own catalog filters apply.

## Integration

- `POST /api/creators/search` takes `{query, home, role}`, with role developer or publisher (the legacy role-less API remains compatible), with a 2-100 character name. It requires the app origin and JSON content type, shares Steam pacing, allows one concurrent discovery request, and caches up to 128 queries for ten minutes. Failures remain errors rather than stale search results.
- The featured three creators remain hardcoded for initial loading.
- Homepage selectors carry numeric clan IDs; credit selectors carry role/name. Catalog requests accept no arbitrary URLs. Query names are encoded. Homepage and credit catalog IDs stay distinct.
- Added creators persist with their catalog cursors/results in the tab; at most 20 creators are displayed. Saved links are reconstructed from validated selectors.
- Existing price caching, comparisons, free-product handling, statistics, cancellation, and refresh are reused. Searching alone performs no price requests.
- This version takes names, not pasted homepage URLs.

## Potential TODO (deferred)

Consider a locally maintained searchable developer/publisher directory with aliases and predictable ranking if Steam suggestions prove insufficient. Evaluate sources, completeness, refresh costs, and maintenance first. No crawler or persistent company index is included now.

## Role tabs (0.4.0-beta)

The frontend keeps independent developer and publisher state and session keys. Featured registry role entries have exact-name selectors, so expansion uses product credits. Old homepage selectors are excluded from migration; explicit role selections retain their compatible catalog positions. Internal creator filenames and legacy API routes remain for compatibility.
