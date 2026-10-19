# Steam loading performance

## Agreed protocol

One measured run of the unchanged version, then one of the implementation.
Use the supplied public wishlist, capped at its first 200 distinct games in Your
Rank order. Freeze those IDs for the second run. Keep profile identifiers and
raw wishlist/results in ignored local QA storage, not this document or Git.

Both runs use PL/PLN against US/USD and DE/EUR, fresh isolated SQLite caches,
normal 1.5-second shared Steam pacing and production retries. Fetch the wishlist
in each run, then apply the frozen 200-game selection in an isolated harness.
The cap belongs to the benchmark only; the application limit remains 1,000.

Submit through the production HTTP job endpoint and poll at the browser's
1.2-second interval. Record first observed row, first priced row, 50/100/200
rows, terminal state, total elapsed time, available/skipped counts, actual HTTP
attempts by service, and retries/errors. These are backend delivery timings,
including polling delay, not browser paint or rendering timings.

The updated run includes fetching best purchase options so its cost is included.
Retain default offers separately and compare their returned prices with baseline
observations; report changes or incomplete coverage rather than assuming every
price stayed fixed between runs. No concurrency or relaxed pacing in either run.

One cold run per version is a practical comparison, not a statistical latency
guarantee. It does not establish warm-cache speed or isolate upstream load.

## Results

Measured on 2026-10-18 locally, using the same fixed 200 distinct wishlist IDs.
Baseline code: commit `aae90ee`, version `0.5.0-beta`. Updated code:
version `0.6.0-beta`, working implementation on `codex/steam-price-batching`.
One run each, with separate empty cache directories.

| Measurement | Before | Updated |
| --- | ---: | ---: |
| Total time for 200 checked games | 815.194 s | 20.664 s |
| First delivered / priced row | 4.897 s | 10.931 s |
| 50 rows delivered | 187.206 s | 10.931 s |
| 100 rows delivered | 394.328 s | 10.931 s |
| appdetails HTTP attempts | 534 | 6 |
| StoreBrowse HTTP attempts | 0 | 6 |
| Wishlist HTTP attempts | 1 | 1 |
| NBP HTTP attempts | 2 | 2 |
| Total HTTP attempts | 537 | 15 |
| HTTP errors | 8 (429) | 0 |
| Games compared in all selected countries | 157 | 158 |
| Games without a supplied regional price | 33 | 34 |
| Games unavailable in a requested country | 8 | 8 |
| Games left with technical failures | 2 | 0 |
| Final state | Partial | Complete |

Overall elapsed time fell by 97.47%: about
39.4 times faster. The new run includes both offer datasets,
not just default-price retrieval. Its twelve Steam data requests exactly match
two 100-item windows × three countries × two endpoints. The first window is
emitted together, explaining why first-row latency increased while delivery of
50/100 rows improved substantially.

For all 157 games comparable in both runs, all three regional current and regular
base prices matched: 471 matching regional price pairs. Two old technical failures
resolved: one became comparable, the other had no supplied price. Prices can change
between runs, but no money-value differences occurred in this common comparable set.
Discount percentages are calculated from regular/current amounts in the new path,
rather than assumed identical to Steam's pre-rounded percentage field.

The updated run also produced 158 complete best-offer comparisons and retained 490
available regional offer observations; 110 country/item observations had no offer.
Some individual offers remain useful even when another country prevents a complete
comparison. Best-offer observations are never silently substituted into default
prices. The sum of attributed per-row network attempts was twelve, matching the
independently instrumented physical Steam data calls.

## Interpretation and next optimization ceiling

The measured gain primarily comes from fewer paced requests. This single run does
not establish a universal 39× speedup: upstream load, cache state, list contents,
and throttling affect both times. The baseline encountered rate limiting; its last
429 preceded its final request by over three minutes. No rate limits were observed
in the updated run. No second measured run was performed.

At the current 100-item limit, the observed twelve-request cold-data floor cannot
be improved just by faster Python parsing. For this 200-game, three-country,
dual-offer workload, a hypothetical safe 200-item batch would reduce it to six;
research found practical appdetails URL/count boundaries below that for some ID
sets, so raising the default to 200 is not justified. Fully fresh caches eliminate
these twelve data requests, but wishlist retrieval and any needed NBP refresh remain.

A smaller initial window could improve time to first row at the cost of additional
requests and somewhat longer total loading. That is the next useful tuning question,
not a change made after this measurement. Five countries are already covered by
deterministic retrieval tests; this live benchmark deliberately used only three.

The existing application server and user cache were not used for either speed run.
An isolated HTTP server imported the original modules before implementation edits;
its running baseline remained the old version. Backend and frontend regression
checks ran separately, and browser layout QA used clearly labeled local fixture
prices. Browser paint, image loading and interactive table rendering are outside
these delivery timings.


Post-benchmark correction: retain suitable Steam discount percentages instead of
always replacing them with calculated values. This adds no network requests.
The measurements above predate that correction; no extra speed run was performed.
