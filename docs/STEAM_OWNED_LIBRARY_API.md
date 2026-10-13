# Owned-library retrieval

Researched 2026-10-13; status updated 2026-10-14.
Prototype retained in 0.5.0-beta, hidden behind an internal flag. Authenticated
live key/library testing is TODO; see the [checklist](ROADMAP.md#deferred-stage-the-users-owned-library).
Normal launches neither initialize the library UI nor accept library job starts.
For isolated QA, WebApplication can opt in with owned_library_enabled=True.
A configured API key alone does not enable the feature.

Valve documents [IPlayerService/GetOwnedGames](https://partner.steamgames.com/doc/webapi/IPlayerService?l=english)
as requiring a user Web API key and visible owned games/game details. Configure
STEAM_WEB_API_KEY in the server terminal. Browser requests never accept keys.

The [Web API overview](https://partner.steamgames.com/doc/webapi_overview)
specifies api.steampowered.com as the public API host. This app uses that host
with verified HTTPS. The partner host needs publisher credentials. Service
arguments use URL-encoded JSON in input_json; key is a separate parameter.
The request sets steamid, include_appinfo=true, include_played_free_games=false.
Custom profile URLs first use the existing ResolveVanityURL adapter.

No pagination cursor is documented. Request the full visible list once, check
game_count against the returned array, and deduplicate app IDs. Malformed or
incomplete responses fail. More than 1,000 distinct games fails explicitly;
no silently truncated library is compared. No ownership mapping is cached on disk.

Explicit game_count=0 completes without rates or price requests. An empty response
object does not distinguish private from otherwise unavailable libraries and is
reported as unavailable. HTTP 401/403 reports a rejected server key; TLS,
network-denial, unreadable-response, vanity, and upstream failures have controlled
messages. URLs, credentials, profiles, response bodies, and raw exception text do
not enter diagnostics. Job attribution remains in private, expiring server memory.

The returned games are not a complete license/DLC inventory. Free-to-play games
are excluded by request; DLC, demos, shared licenses, software, and removed games
are not promised complete coverage. Steam can hide individual private games;
see [Steam Private Games](https://help.steampowered.com/en/faqs/view/1150-C06F-4D62-4966).
The app reads no login cookies and changes no privacy settings. Games without
current prices follow the existing unavailable/uncompared handling.

Name is the default loading order; Steam order preserves the returned list and
does not imply purchase dates, playtime, or wishlist priority. Missing names use
existing baseline name prefetch. Prices represent current offers, not amounts paid.

Anonymous probes on 2026-10-13 returned HTTP 401 from keyless GetOwnedGames and
redirected both the games page and its legacy XML variant to sign-in. These
checks support the documented credentialed route. A user-supplied profile was
used only for local live QA and is absent from tracked tests/fixtures.
Authenticated live retrieval remains unverified and is deferred until Steam
Guard/key setup is available. Retain automated fixtures, then complete the live
checklist before enabling the feature for normal use.
