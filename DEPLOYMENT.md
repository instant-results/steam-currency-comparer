# Public hosting path

The source is published on [GitHub](https://github.com/instant-results/steam-currency-comparer).
The app itself is still local; no public service has been deployed. The Python service and browser assets can be deployed
together on a host that supports a persistent Python process. There is no
separate frontend build and no browser-side API key.

## Run locally

```powershell
python -m pip install -r requirements.txt
python serve_web.py
```

Open http://127.0.0.1:8765. The local launcher listens only on the loopback
interface. Example mode compares seven selected games using live Steam prices and NBP
exchange rates; it requires outbound network access.

## Serve with a production WSGI server

Install the optional hosting dependency, configure the exact browser origin,
and run one server process:

```powershell
python -m pip install -r requirements-web.txt
$env:WEB_ORIGIN = "https://your-domain.example"
$env:STEAM_PRICE_POLISHER_DATA_DIR = "C:\data\steam-price-polisher"
waitress-serve --listen=127.0.0.1:8765 --threads=4 --max-request-body-size=2048 --call steam_price_polisher.web_app:create_app
```

On Linux, set the same environment variables using your hosting platform and
use a writable persistent data directory such as `/var/lib/steam-price-polisher`.
The service account must be able to write to that directory. Mount this directory
on persistent storage if deploying a container.

Place the service behind an HTTPS reverse proxy. Preserve the public Host
header, set request/body/time limits, and rate-limit job creation at the proxy.
`WEB_ORIGIN` must exactly match the public scheme and hostname (including a
nonstandard port, when applicable). Requests with other Host headers or POST
origins are rejected. Configure the proxy's health check to use that Host header
when requesting `GET /api/health`.

If client IPs are forwarded, configure Waitress to trust **only the actual
proxy IP**, using `--trusted-proxy=PROXY_IP` and
`--trusted-proxy-headers=x-forwarded-for`. Do not trust arbitrary forwarded
headers from public clients. Without this setting, all clients behind the proxy
share the app's per-connection limit.

See the [Waitress runner documentation](https://docs.pylonsproject.org/projects/waitress/en/stable/runner.html)
for the production server and proxy settings.

## Current operational boundaries

- Run **one process / one replica**. Job ownership and the paced analysis queue
  are in memory. Multiple web threads are supported; multiple processes require
  a shared job store and distributed Steam pacing first.
- One analysis runs at a time. The queue and retained results are bounded to 20
  jobs total. Results expire after one hour. The limit is intentionally small
  for this first version; busy clients receive a retryable HTTP 429 response.
- One unfinished job per client connection/IP, at most three recent jobs per
  minute, and at most 1,000 wishlist games per analysis. Large cold wishlists can
  take many minutes because Steam calls are paced at 1.5-second intervals.
- Cancellation is cooperative: an in-flight request may finish before the
  worker stops. Completed prices remain cached for the next attempt.
- Results use unguessable job IDs **and** separate bearer tokens. There is no
  public result listing. Tokens stay in tab-scoped session storage, allowing refresh to reconnect.
  Closing the tab loses access. Server restarts lose jobs, but retain the price cache.
  Profile input and selected regions are stored with the job token in tab-scoped
  session storage to restore attribution and retry settings.
- Public wishlists only. The web service ignores `STEAM_COOKIE` and never reads
  `wishlist.txt`. Optional `STEAM_WEB_API_KEY` is server-side configuration for
  vanity URLs; the browser cannot submit keys or cookies.
- Profile attribution remains in the private result until it expires (one hour). The SQLite
  database stores game prices and exchange rates, not profile-to-wishlist links.
- Do not log request bodies or Authorization headers at the proxy. The local
  launcher disables access logs, and browser error messages omit raw upstream
  exceptions, request URLs, and local paths.

Before opening to the public, configure HTTPS, persistent storage, trusted proxy
handling, and edge abuse controls on the chosen host. Run a live public wishlist
smoke test and measure request limits there. A local bounded live test retrieved 755 wishlist games and compared three of
them successfully. Repeat this check on the deployment host; a full-wishlist
run and production load test remain outstanding. A separate seven-game live
example completed locally on 2026-09-23 for the README screenshots; that was
not a public-host load test.


## Work remaining before a public beta

The intended hosting direction is a free public website with a few non-intrusive
ads, potentially covering operating costs. Accounts, subscriptions, and billing
are not part of the agreed direction. Hosting and advertising are not implemented.

The current code still needs a focused service-readiness review:

- Address long jobs blocking the single worker, with measured scan limits and
  queue fairness. More replicas require shared job state and Steam pacing.
- Separate completed-result retention from admission capacity: the 20-job limit
  currently includes completed jobs, even when the worker is idle.
- Review throttling and retry behavior. Web retries cap delays at 15 seconds,
  including numeric upstream `Retry-After` values; date-form values are not parsed.
- Add useful worker/queue/cache monitoring, deployment and rollback procedures,
  storage maintenance, and abuse controls. `/api/health` reports application
  status and version, but does not establish worker or upstream health.
- Decide whether jobs should survive restarts. Today only cached prices and
  exchange rates persist.
- Recheck applicable data-use terms, privacy disclosures, and any selected ad
  provider's requirements before hosting. External ads would require narrowly
  scoped changes to the current Content Security Policy.

These are planning notes, not completed safeguards or authorization to deploy.
