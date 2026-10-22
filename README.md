# Steam Currency Comparer

**Version: 0.7.2** · Beta for local use.

[GitHub repository](https://github.com/instant-results/steam-currency-comparer)

Compare the prices of games on your public Steam wishlist, or browse featured
developer and publisher catalogs, across regional Steam storefronts. Choose a baseline currency and up to 36 other storefronts; the app
converts their prices using National Bank of Poland (NBP) exchange rates and shows
which games cost more or less in your baseline storefront, including current sales.

This is a **locally run web app**: a small Python server runs on your computer,
and you use it in your browser. You need Python and a terminal to set it up, but
no programming knowledge to use it. There is no hosted service or packaged
installer yet. Independent project; not affiliated with Valve or Steam.

## Preview

![Steam Currency Comparer showing a completed example comparison with regional prices and percentage differences](docs/images/example-comparison.jpg)

Live seven-game example captured on 2026-09-23 with version 0.1.0-beta.1;
the screenshot shows part of the completed results. Prices and exchange rates
change over time. No personal Steam profile is used.
[View the app title and setup screen](docs/images/app-overview.jpg).

## What it does

- Compares 37 currencies using one representative Steam storefront per currency.
  Any can be the baseline, with up to 36 alternatives. Search the currency picker
  or choose Select all; the default is PLN against USD and EUR.
  See the [supported storefronts](docs/STOREFRONTS.md).
- Keeps currency selection above the full-width comparison. The selectors collapse
  when a comparison starts; **Change currencies** reopens them. The selection
  summary and its reopen button remain visible while browsing results.
  **Update currencies** appears inside the expanded panel; **Hide currencies**
  discards unapplied edits and restores the displayed selection.
  Desktop tables give artwork and long game titles more room; narrow screens keep
  game identity above the price row.
- Keeps game/title, baseline and DIFFERENCE visible while regional price columns
  scroll horizontally. A blue scrollbar above the results spans only the regional
  columns and stays available while scrolling down the comparison. Catalog tables
  share the same scroll position. Currency/country titles stay visible beneath the
  scrollbar while scrolling through results.
- Shows converted regional prices alongside muted original-currency prices,
  right-aligned currency codes, discounts, and absolute and
  percentage differences.
- Optionally shows Steam's best purchase offers alongside default game prices,
  identifying packages and bundles separately. Find the checkbox directly above
  the table in each tab. Toggling it uses already
  loaded data; filters and totals continue to describe default game offers.
- Retrieves prices in batches. A single 200-game cold-cache measurement took
  20.7 seconds versus 13 minutes 35 seconds previously; first results arrived in
  10.9 seconds versus 4.9 seconds. See the [test protocol and limitations](docs/STEAM_PRICE_PERFORMANCE.md).
- Loads games by Your Rank, Date Added, or Name, with search, filters, and
  result sorting once results arrive.
  Table headers cycle ascending, descending and original loading order; compact
  blue indicators show the active direction. Wishlist search sits below Game name.
- Caches prices and exchange rates, labels stale results, and lets you cancel
  or retry a comparison.
- Fetches both NBP exchange-rate tables (A and B) upfront and caches all rates for
  reuse. Each fresh table is reused for 24 hours; failures are handled independently.
  After loading, use **Update currencies** to recompare the current tab without
  reloading its game list. Cached Steam observations are reused; missing or expired
  selected-country data is fetched while the previous comparison stays visible.
- Exports wishlist, developer, and publisher results with one CSV schema, including
  both credit lists, regional prices, comparison details, and provenance.
  Wishlist profile attribution is optional and off by default.
- Wishlist rows show compact Developer and Publisher credits beneath each game's
  artwork/title, including all reported names and labels for unavailable metadata.
- Separate **Developers** and **Publishers** tabs compare featured games without
  a wishlist. Developers starts with Supergiant Games, CD PROJEKT RED, and
  Techland. Publishers starts with Devolver Digital (US), THQ Nordic (Austria),
  and 11 bit studios (Poland). **Load more** expands the products
  credited to each name in that role, including paid DLC and soundtracks.
  Free products are hidden after checking.
- Each catalog's summary shows average and median percentage differences for
  each comparison currency, sample sizes, and coverage of loaded products.
  Statistics cover the displayed selection rather than the entire catalog.
- Each tab searches its own role and offers **Add & compare** for matching names.
  Developer and publisher selections, results, and catalog positions are saved
  independently in the same browser tab. Developer/publisher credits appear
  beneath each game, or in a separate column using **Show publisher column** /
  **Show developer column**. There is no separate creator category.

The app compares prices for information. It does not change your Steam account's
country, modify your wishlist, or purchase games. Displayed regional differences
are not a guarantee that you can buy at another storefront's price.

## Run locally

### Requirements

- **Python 3.10 or newer**, with pip and support for virtual environments.
- A web browser and internet access to Steam and NBP.
- Your **public Steam wishlist**, or use the built-in example to try the app.

Wishlist comparisons need no Steam sign-in, Steam cookies, or API key when using a numeric
SteamID64 or a `/profiles/` URL. Custom `/id/` URLs need optional API-key setup.
The owned-library prototype is hidden by default pending authenticated live
API testing. An API key does not enable it. See the [deferred stage](docs/ROADMAP.md#deferred-stage-the-users-owned-library).
Node.js is only needed for frontend tests, not to run the app.

### 1. Get the project

Download the repository using **Code → Download ZIP** on GitHub and extract it,
or clone it with Git:

```sh
git clone https://github.com/instant-results/steam-currency-comparer.git
cd steam-currency-comparer
```

Open a terminal in the extracted or cloned project folder (the folder containing
`serve_web.py` and `requirements.txt`).

### 2. Install and start

Use the commands for your operating system. A virtual environment keeps the
project's dependencies separate from other Python applications. These commands
use its Python directly, so activation is not required.

**Windows — PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe serve_web.py
```

If `py` is unavailable but Python is installed, use `python -m venv .venv`
for the first command. Ensure that interpreter is Python 3.10 or newer.

**macOS / Linux — terminal**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python serve_web.py
```

If your Linux installation reports that `venv` or `ensurepip` is missing,
install your distribution's Python virtual-environment package, then retry.

### 3. Open the app

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)** in your browser.

A fresh visit automatically compares seven selected games without a profile.
An existing wishlist comparison is restored first.

1. Enter your 17-digit SteamID64 or your numeric Steam profile URL to compare
   your own public wishlist.
2. Select a baseline and one or more comparison currencies.
3. Choose the loading order and click **Compare regional prices**.

The example uses live Steam prices and NBP exchange rates, so it also needs
internet access. A numeric profile URL has the form
`https://steamcommunity.com/profiles/YOUR_STEAMID64/`; replace `YOUR_STEAMID64`
with your actual ID. The numeric ID `76561198000000000` used in documentation
and tests is a placeholder, not a supplied demo profile.

Keep the terminal open while using the app. Stop it with **Ctrl+C**. On later
visits, run only the final server command for your operating system; repeat
installation if the project's dependencies change.

## What to expect

- **Public wishlists only**, with at most 1,000 games per comparison in the web app.
- **More storefronts take more time.** Steam requests are paced at 1.5-second
  intervals and data is retrieved in batches. A cold 100-game window across all
  37 storefronts normally needs 74 data requests before retries or URL-driven
  splitting. Cached prices reduce work; the three-storefront performance example
  above does not predict an all-storefront comparison time.
- **Name order may start slowly:** it first fetches missing game names from the
  baseline storefront. Your Rank is the default.
- **Unavailable products are hidden by default.** Enable **Show unavailable
  products** to reveal them. Technical failures remain visible.
- **Results are temporary.** Refresh reconnects in the same tab; closing the tab
  or restarting the server loses job access. Server results expire after an hour;
  completed catalog results saved in the tab remain visible until refreshed or closed.
- **Prices are snapshots.** Regular prices normally refresh after an hour, sale
  prices after 15 minutes, and exchange rates after 24 hours. Stale fallback is
  labeled when available.

The comparison uses final prices, including sales, and NBP currency conversion.
It does not adjust for tax differences or payment-provider fees. Germany is the
selected EUR storefront, not a guarantee of prices across the euro area.
See the [comparison methodology](docs/USAGE.md#rates-and-comparison-methodology)
for the exact interpretation of results.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Python is not found | Install Python 3.10+ and reopen the terminal. On Windows, try `python` if `py` is unavailable. |
| Missing Python module | Run the dependency-install command above, then start the server using that same virtual environment. |
| No public wishlist found | Check your wishlist's visibility and use your actual numeric SteamID64. |
| Custom profile URL cannot be resolved | Use a numeric `/profiles/` URL or configure your own optional Steam Web API key. |
| Port 8765 is already in use | Stop the existing instance or append `--port 8766` to the server command and open `http://127.0.0.1:8766`. |
| Network access denied | Allow the server outbound access through your firewall or execution environment, then restart it. |

Custom profile URL setup is covered in the [usage guide](docs/USAGE.md#custom-steam-profile-urls).
The project does **not** automatically load `.env`; `.env.example` documents
settings that must be supplied as environment variables.

## Local data and privacy

The web app keeps its price cache and diagnostic logs in `.steam-price-polisher/`
by default. The cache stores regional prices and exchange rates, not
profile-to-wishlist links. Logs exclude profiles, API keys, cookies, and job tokens.
The browser tab stores the current profile and job-access token in session storage,
plus separate developer and publisher results and catalog positions. Wishlist
results and profile attribution are held temporarily in server memory. Previously
saved library state is left untouched while its feature is disabled; it triggers
no library requests or control locking.

Steam and NBP receive the requests needed for the comparison, and the browser
loads game artwork directly from Steam's image CDN. Running locally does not mean
running offline. The web app never reads local `wishlist.txt` or `STEAM_COOKIE`.
Keep local data, populated environment files, and credentials out of Git.

## Versioning

The version is defined in `steam_price_polisher/version.py` and shown in the app
header, server startup message, and `/api/health` response. The intended first
stable release is **1.0.0**.

Current releases use **0.MINOR.PATCH**; beta status is documented separately
until the stable release:

- Increment **MINOR** for a substantial new feature and reset PATCH to zero:
  `0.7.2` → `0.8.0`.
- Increment **PATCH** for fixes and refinements within the current feature
  milestone: `0.7.1` → `0.7.2`.
- Releases through `0.7.0-beta` used a beta suffix. From `0.7.1`, version numbers
  omit that suffix; earlier release names remain unchanged.
- Use **1.0.0** when the app reaches the intended stable
  release. After that, use patch versions for fixes, minor versions for compatible
  features, and major versions for incompatible changes.

The current version retains an owned-library prototype introduced in `0.5.0-beta`,
with independent state and the shared comparison layout. Its tab, profile form,
initialization and job submission are disabled by default until authenticated live testing is
complete. Your wishlist, Developers, and Publishers remain available.
Completed and deferred work is described in the
[development roadmap](docs/ROADMAP.md).
It does not imply a planned stable `0.4.0` release. The historical
`0.1.0-beta.1` version predates this convention and remains unchanged in earlier
release notes and screenshot captions.

Update this README and the [changelog](CHANGELOG.md) when changing the version.
Git tags, GitHub releases, and deployment are separate actions; a version bump or commit
does not publish the app.

## Planned development

The three available tabs share a CSV schema. Owned-library code and automated
coverage are retained behind an internal flag; successful authenticated live
retrieval remains TODO. See the [roadmap](docs/ROADMAP.md) for validation criteria
before considering the feature available.

## For developers

The display name is Steam Currency Comparer. Existing filenames, the
`steam_price_polisher` package, and `STEAM_PRICE_POLISHER_*` settings retain
their original names for compatibility.

The backend uses Python WSGI and SQLite; the frontend is plain HTML, CSS, and
JavaScript with no build step. Wishlist retrieval, regional pricing, exchange
rates, comparison arithmetic, and request pacing are separate modules in
`steam_price_polisher/`. Browser assets are in `web/` and regression tests in `tests/`.

Run the Python suite with your virtual environment's interpreter:

```powershell
# Windows
.\.venv\Scripts\python.exe -m unittest discover -v
```

```sh
# macOS / Linux
.venv/bin/python -m unittest discover -v
```

Frontend checks require Node.js with its built-in test runner:

```sh
node --test tests/test_web_render.cjs
node --check web/app.js
node --check web/creators.js
node --check web/library.js
```

- [Usage and technical reference](docs/USAGE.md): CLI commands, sale-price handling,
  CSV fields, sorting, caching, diagnostics, and methodology.
- [Deployment guidance](DEPLOYMENT.md): requirements and limitations for future
  public hosting. The local launcher is not the public deployment entry point.
- [Development roadmap](docs/ROADMAP.md): next targets and the subsequent owned-library stage.
- [Text and localization decisions](docs/TEXT_AND_LOCALIZATION.md): wording,
  credit alignment, and boundaries for future translations.
- [Frontend design decisions](docs/DESIGN_DECISIONS.md): shared field-caption
  spacing and where it applies.
- [Sorted wishlist API research](docs/STEAM_SORTED_WISHLIST_API.md): proposed
  integration, not an implemented feature.
