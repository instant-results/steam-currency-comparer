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

Pending the baseline and updated measurements.
