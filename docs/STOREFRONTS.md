# Supported storefronts and the comparison matrix

Updated: 2026-10-22. The app supports 37 live Steam currencies, with one
representative country per currency. Any can be the baseline; select one to 36
others. The default remains PLN against USD/EUR.

Available in `0.7.0-beta`, integrated into `main` through
[PR #1](https://github.com/instant-results/steam-currency-comparer/pull/1).

Use the searchable currency panel above the comparison to find a currency or
country. Selectors collapse when a comparison starts or saved results are restored;
Change currencies reopens them from beside the selection summary. Update currencies
appears only while expanded. Hide currencies discards unapplied edits and restores
the active tab's displayed currencies; automatic collapse during a run preserves
the submitted selection.
The picker lists sit side by side above 600px and stack on smaller screens. Select all
chooses every alternative to the current baseline; Clear removes alternatives.
Searching hides choices without changing their selection. Changing the baseline
excludes that country from alternatives while retaining temporarily conflicting
preferences; Select all can fill the remaining choices again. After loading,
Update currencies applies the choices to the current tab.

## Table behavior

Baseline and comparison selection cards show locally bundled circular flags.
EUR uses the EU flag as a currency cue; Germany remains its price source and
visible country label. Other flags identify the representative country.
Currency/country text remains available independently of the decorative flags.

Game/title and baseline stay pinned on the left, and DIFFERENCE stays pinned on
the right. The comparison uses the workspace's full width. Desktop identity
columns normally adapt between 300px and 480px, growing further when needed to
fill unused space if all selected storefronts fit. Narrow screens keep identity
above prices.
The main column headings share a vertical centre on desktop. OTHER
STOREFRONTS and its conversion caption remain fixed horizontally; the individual
currency/country labels occupy a separate row below and scroll with the prices.
Once that row reaches the sticky scrollbar, its titles remain visible directly
beneath it while scrolling through results. They keep the same horizontal offset,
including across catalog tables, and stop following at the comparison boundary.
Titles remain available when all columns fit without a scrollbar. Country labels
include the country code after a middle dot (for example, United States · US).
Each regional price cell shows the converted price on the left and a muted
original price on the right. Currency codes line up at the right edge across
rows, independent of the number of digits. Long original prices can wrap below
the converted amount on narrow screens while retaining their right alignment.
Best-offer blocks share a vertical start and label/price/name heights within
each game, so wrapped defaults and unavailable offers do not shift the other
storefronts. Following offer sale details align after the shared name band.
Regional currency headings, default prices and best offers use the same ordered,
fixed-width slots between them. The blue horizontal scrollbar sits above the list,
spans only the visible regional columns, and stays at the viewport top while
scrolling through the comparison. It stops following at the section's end.
Currency-picker scrollbars use the same blue treatment. Scroll with the top
scrollbar, a trackpad, or arrow keys after focusing the table or scrollbar.
Catalog currency headings and all catalog tables synchronize their horizontal
position. Filters, sorts,
per-tab completed/pending snapshots and CSV keep their existing behavior.

At narrow widths the pinned game/title occupies a full-width row above prices;
baseline and DIFFERENCE remain at the left/right edges of the price row. Optional
catalog credits occupy another identity row. This leaves space for regional prices
without compressing text or widening the page. Desktop optional credit columns
stay with the pinned identity.

Catalog summaries show per-currency average/median/sample sizes. With more than
four alternatives these metrics are grouped under expandable Regional statistics.
The overall DIFFERENCE still compares the baseline with the cheapest selected
alternative and now identifies that storefront. Missing required regional prices
still make a product uncompared; Show unavailable products and retained partial
best offers use the existing rules. More countries do not change that arithmetic.

With one or two comparison currencies, the desktop regional area keeps a 510px
minimum. A single currency uses a centered 255px content slot; two use 255px each.
With three or more, each slot is 170px. Labels, prices and both offer sets share
these positions. The existing narrow layout uses 125px regional slots.

## Registry

`steam_price_polisher/storefronts.json` is the shared registry for configuration,
API validation and browser choices. The server injects its escaped JSON into the
HTML; the frontend does not maintain a second country/currency mapping. US is the
only USD representative and Germany remains the EUR representative. Regional USD
pricing groups (CIS, LATAM, MENA, South Asia) are excluded from this stage.

| Currency | Representative country | Country code |
| --- | --- | --- |
| AED | United Arab Emirates | AE |
| AUD | Australia | AU |
| BRL | Brazil | BR |
| CAD | Canada | CA |
| CHF | Switzerland | CH |
| CLP | Chile | CL |
| CNY | China | CN |
| COP | Colombia | CO |
| CRC | Costa Rica | CR |
| EUR | Germany | DE |
| GBP | United Kingdom | GB |
| HKD | Hong Kong | HK |
| IDR | Indonesia | ID |
| ILS | Israel | IL |
| INR | India | IN |
| JPY | Japan | JP |
| KRW | South Korea | KR |
| KWD | Kuwait | KW |
| KZT | Kazakhstan | KZ |
| MXN | Mexico | MX |
| MYR | Malaysia | MY |
| NOK | Norway | NO |
| NZD | New Zealand | NZ |
| PEN | Peru | PE |
| PHP | Philippines | PH |
| PLN | Poland | PL |
| QAR | Qatar | QA |
| RUB | Russia | RU |
| SAR | Saudi Arabia | SA |
| SGD | Singapore | SG |
| THB | Thailand | TH |
| TWD | Taiwan | TW |
| UAH | Ukraine | UA |
| USD | United States | US |
| UYU | Uruguay | UY |
| VND | Vietnam | VN |
| ZAR | South Africa | ZA |

## Sources and validation

- [Valve supported currencies](https://partner.steamgames.com/doc/store/pricing/currencies):
  live currencies, regional USD groups and amount units. Currency enum identifiers
  also include legacy/non-live entries and are not the supported list.
- [NBP API](https://api.nbp.pl/en.html), latest complete tables A and B: all 37
  currencies were covered in the 2026-10-20 validation, including PLN identity.
- Live production-client checks on 2026-10-20 queried public Stardew Valley/Hades
  IDs (413150/1145360) in all 37 countries. Returned price currencies matched all
  representatives; price and StoreBrowse parsing produced no errors. The check
  used normal 1.5-second pacing and retries, with no user profile or wishlist.
  Local aggregate results are ignored in .steam-price-polisher/qa/storefront-validation.json.

Steam appdetails and StoreBrowse amounts continue to use hundredths, including
JPY, KRW and KWD. Do not substitute native ISO minor-unit rules (for example,
KWD thousandths) for Steam's protocol units. Explicit appdetails currency mismatches
remain errors. StoreBrowse still attributes currency to its requested storefront
because its response does not supply an independent currency code.

Initial loading fetches selected countries only. Post-load updates reuse fresh
observations and fetch missing/expired selected-country data, retaining default
and best offers independently. Work grows with selected countries; batch sizing,
pacing, retry budgets, cache freshness and cancellation rules are unchanged.
The live sample establishes regional compatibility, not universal availability
for every product or a performance guarantee for 37-country comparisons.
