# Steam price batching - implementation plan

Updated: 2026-10-18. Branch: `codex/steam-price-batching`.
Status: approved for implementation, following one baseline performance run.
Evidence, observed limits, and the optimization ceiling are in
[the research document](STEAM_PRICE_BATCHING.md).

## Scope and decisions

- One hybrid pipeline for every nonempty list: StoreBrowse metadata batches,
  followed by appdetails price-only batches for the requested countries.
- No special single-game/small-list fast path. A batch of one uses the same
  provider/parser/cache/progress machinery as larger batches. The one extra
  cold metadata request is an accepted simplicity trade-off.
- Default maximum 100 games per request, independently configurable for metadata
  and prices. Also enforce an encoded full-URL budget (proposed initial 6,000
  bytes) before sending. These are operational guardrails, not Valve guarantees.
- Keep shared pacing, backoff, job locking, current comparison semantics, and
  existing UI/API currency limits. Add an optional checkbox for separately labeled
  Steam best-offer comparisons. Do not add concurrency, new storefronts, automatic
  example loading, dynamic currency switching, or unrelated frontend layout work here.
- Retrieval accepts a collection of supported storefronts without assuming a
  maximum of three. Public comparison validation still enforces one baseline
  plus one or two alternatives. Baseline-only submission remains invalid.
- Preserve appdetails price semantics initially. The user's discount reference
  is the same offer's regular base price; offer/bundle selection remains a
  separate observation. Retain default offers and additionally retrieve Steam-selected
  purchase options. A checkbox shows their separate comparison; never silently
  substitute a bundle into the default-offer comparison. Preserve offer identity
  and leave regular-price discounts unavailable when the source cannot establish them.

## 1. Define the backend contracts and batch planner

Relevant modules: configuration.py, models.py, steam_access.py, analysis.py.

Define independent metadata and regional-price observations, including explicit
completeness, source, fetch time, and per-item error state. Key price observations
by app ID and country, with a validated currency. Metadata retains context/language
and field-known status, with provenance for reuse across requested countries.
Do not treat metadata obtained in one country as proof of sale availability there
or elsewhere. A restricted response cannot globally overwrite known good metadata.

A pure planner deduplicates requested IDs, retains their output order, removes
fresh cache hits, and chunks remaining work using both item count and the actual
encoded URL length. It accepts one item naturally. Constructing an empty batch
must produce no network request. Keep country identity separate from currency
identity to support future storefronts sharing a currency.

Acceptance: deterministic batches never exceed either configured budget, and
retrieval-level tests exercise one, two, five, and more storefronts independently
of the public UI selection cap.

## 2. Implement and validate the two batch adapters

Relevant modules: steam_access.py, http_client.py, request_policy.py.

StoreBrowse metadata requests include basic info and explicitly disable best
purchase options. Match response records by requested ID and item type. Interpret
successful metadata, missing creator fields, free status, region restrictions,
and invalid IDs without conflating absent data with a definite false value.

appdetails requests use only price_overview, one country per request. Validate
currency, amounts, base price, discount, and each returned ID. Handle the observed
successful empty-array response as no supplied price, not proof of a free game.
HTTP 200 with an empty body is a protocol failure, not a completed empty batch.

Return independent per-item outcomes. Missing/duplicate/unexpected entries cannot
silently shift rows or mark every item unavailable. Preserve valid sibling data
where the response allows it and recover only unresolved work.

Acceptance: fixtures cover regular/sale prices, credits, free/DLC/soundtrack items,
region mismatches/restrictions, missing/reordered/duplicate records, malformed
payloads, and empty successful HTTP responses. StoreBrowse bundle/compliance price
fields must never replace appdetails price observations through metadata joins.

## 3. Decouple metadata caching from price freshness

Relevant modules: cache.py, price_service.py.

Add a versioned metadata cache with independent completeness and timestamps;
retain regional price freshness and the existing regular/sale/unavailable TTLs.
Choose and document a metadata TTL independently (initial proposal: 24 hours).
Do not reset metadata age during a price refresh, erase known credits with an
unrequested field, or repeatedly fetch valid responses with unavailable credits.
Do not infer permanent free status from an absent price or a temporary promotion.

Migrate existing cached observations without fabricating metadata provenance or
freshness. Older entries with insufficient metadata can be enriched once. Join
metadata at the service boundary to preserve the current result/CSV contract.
Cache writes for successfully fetched siblings must survive a later batch failure.

Acceptance: migration, stale fallback, absent-versus-known-empty metadata, partial
success, and repeat runs produce correct records and avoid unnecessary requests.
Keep local network permission denial non-retryable and do not conceal it with stale
fallback. Store no profile-to-game or ownership mapping in the metadata cache.

## 4. Integrate ordered progress and bounded recovery

Relevant modules: analysis.py, web_app.py, creators.py, owned_library.py,
request_policy.py, event_log.py (only where their integration requires changes).

Route wishlist, example, catalog, and internally enabled library comparisons
through the same batch service. Fetch metadata needed for Name order first;
other orders can work through bounded windows. Fetch required countries for a
window, then emit the current per-game progress format in the requested order.
Continue excluding free catalog products only with sufficient metadata evidence.

Cancel before every request, split/fallback, and progress emission. Retry jobs
reuse successfully cached data. Preserve existing one-worker and cross-tab locks.
Use the normal bounded transient retry policy before considering split recovery.
A 429/Retry-After response defers the shared schedule; it must not trigger a burst
of split requests. Local denial/TLS/configuration errors must not produce a split
storm. Deterministic 414 or persistent batch-shape failures may shrink batches.

Recovery needs a finite HTTP-attempt budget shared by split children and fallbacks,
not a fresh full retry allowance at every node. Set the budget explicitly during
implementation and cover exhaustion; report unresolved items as failures rather
than dropping them. Singleton requests may be recovery leaves or metadata
fallbacks, never an optimization selected because the original list is small.
Avoid persisting a globally reduced batch size after one unexplained 5xx response.

Acceptance: cancellation, bounded request counts, partial recovery, backoff,
retry/cache reuse, and stable ordering are covered without additional UI flows.

## 5. Keep diagnostics and exports honest

Count HTTP attempts separately from item-country observations and cache hits.
One 100-game batch is one request, not 100. Review how existing per-row counters
and repeated CSV storefront rows represent shared fetches; do not duplicate a
physical batch count across every product and call the sum network traffic.
Document the attribution policy without changing CSV headers in this stage.

Log aggregate batch size, duration, successes, misses, and fallback attempts.
Retain current restrictions on profiles, credentials, request URLs, response
bodies, and private paths. Avoid adding a performance dashboard or UI controls.

Acceptance: request accounting reconciles with actual HTTP calls, and existing
provenance and privacy expectations remain valid.

## 6. Regression checks and limited live measurement

Run the Python suite and the existing frontend regression/syntax checks required
by changed contracts. Add meaningful deterministic tests for the adapter, planner,
cache, error, and job behaviors above; no permanent network-dependent test suite.

Use public samples for limited live verification. Measure both time to first
usable row and total completion, with cold/fresh/mixed caches and batches of
25/50/100. Include one game, the example list, and a representative larger list;
compare two, three, and five supported storefronts. Test more storefronts in the
backend with fixtures; validate any new real country separately before enabling it.

Compare every returned price tuple against the existing source semantics, keeping
the observations close enough in time to identify price changes. Do not infer a
throughput guarantee from a handful of successful requests. Keep probes, raw
responses, caches, and runtime files ignored.

Start at the configurable 100-item default. Change it only on measured evidence
of latency, reliability, URL length, payload size, and cancellation responsiveness.
A smaller first window or bounded concurrency is later tuning, not a prerequisite.

## Completion criteria and Git delivery

The backend reduces redundant HTTP calls while maintaining result correctness,
existing user behavior, cache freshness, cancellation, and diagnostics. The same
pipeline works for one game and many, with no hard-coded three-storefront ceiling
inside retrieval. Broken batches fail visibly within bounded request budgets.

Implementation is authorized. First record the unchanged baseline, then implement
 and run the same 200-game measurement. See STEAM_PRICE_PERFORMANCE.md.
When committing implementation work after authorization, keep feature and test
changes in separate coherent commits, with documentation updated for actual
behavior. The planning/research documents are committed before application changes. No push,
release, deployment, or change to the owned-library visibility is authorized.
