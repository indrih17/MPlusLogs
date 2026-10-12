# MPlusLogs public profile service

The service is ready for local Docker deployment. No hosted endpoint is bundled
yet. Existing Companion installations keep using protected direct WCL access
until explicitly configured for this service.

## Local Docker start

Create a **confidential server-side WCL client** at
https://www.warcraftlogs.com/api/clients and register this exact redirect URI:
`http://localhost:8080/auth/callback`. Do not enable a public desktop/PKCE client
for the server credentials. Keep its secret on the server only.

From a source checkout **outside the WoW installation**:

```powershell
Copy-Item server/.env.example server/.env
# Edit server/.env locally: set WCL_CLIENT_ID and WCL_CLIENT_SECRET.
docker compose --env-file server/.env -f server/compose.yaml up --build -d
Invoke-RestMethod http://localhost:8080/healthz
```

Launch the released Companion with:

```powershell
& 'C:/path/to/MPlusLogs-Companion.exe' --service-url http://localhost:8080
```

Alternatively set `MPLUSLOGS_SERVICE_URL` before starting Companion. Successful
sign-in persists the selected URL together with a Windows DPAPI-protected service
session. The browser authorizes WCL on its own site; the backend exchanges the
authorization code and reads only `userData.currentUser.id`. WCL user tokens are
never given to Companion, stored on disk, or used for the shared profile cache.
The backend issues its own revocable, hashed, 30-day sessions. Re-login does not
reset an account's usage. An authorization ticket is single-use and expires in
five minutes.

## Production with HTTPS

1. Set DNS to the chosen host and open ports 80 and 443.
2. Set `MPLUSLOGS_DOMAIN=profiles.example.com` in `server/.env`.
3. Register `https://profiles.example.com/auth/callback` for the confidential WCL
   client. Replace `profiles.example.com` with the actual DNS name everywhere.
4. Run the production file **on its own**, not as a Compose override:

```sh
docker compose --env-file server/.env -f server/compose.production.yaml up --build -d
```

Caddy obtains TLS certificates. The application port is not published; Caddy
overwrites `X-Real-IP`. Never expose the application directly when
`MPLUSLOGS_TRUST_PROXY=1`. Access logging is disabled to avoid recording OAuth
codes. The client requires HTTPS except for loopback testing, refuses HTTP
redirects for API calls, and never falls back to direct WCL when server mode is
configured.

Before moving a shared WCL quota behind this service, verify with WCL whether it
is scoped to a client, its owner, or the logged-in account. Retire the old direct
access path/client where it can still consume the same quota. Adding a proxy
alone cannot prevent callers from using a still-active public PKCE client
directly. Existing installations must be migrated to the configured server URL;
the backend secret must never be embedded in the addon or Companion.

## Cache and admission policy

- Public `/api/v2/client` character rankings only; no private reports or arbitrary
  GraphQL queries. Supported requests contain name, localized realm, region and
  an optional recognized specialization. Zone/season and the dual metric query
  are fixed by the adapter.
- Successful dual DPS/HPS replies: 24 hours. Valid no-profile responses: six
  hours. Temporary errors: five-minute per-profile backoff, preserving good data.
  Stale fallback is limited to seven days; an hourly sweep removes older raw
  profiles and expired missing-log records from disk.
- The cache key includes region, resolved realm slug, normalized name, season,
  zone, specialization, query version and authorization scope. Display role and
  primary metric are excluded. Account-specific direct caches are never reused
  for the public service or another account.
- One in-flight job per cache key across all accounts. Cache reads do not consume
  the account's upstream-load allowance. Only the account initiating a real WCL
  attempt pays that allowance; joiners receive the same public result.
- Defaults: 60 WCL loads/hour and 300/day per verified WCL account; 500 actual
  upstream attempts/hour globally; 300 API reads/minute per account; 600/minute
  per IP; ten login starts/hour per IP. The global attempt count includes login
  identity queries. Account and global limits survive service restart.
  Login starts are additionally capped at 240/hour globally and 2,048 pending
  tickets. One-time bearer delivery is kept only in memory, not in SQLite pages.
- Eight in-flight profiles per initiating account, 128 globally, round-robin
  scheduling between accounts, 180-second queue expiry and bounded result
  retention. A client cannot monopolize the worker with a large batch.
- WCL responses update the global point budget even when the character has no
  logs. Preserve at least 100 points or 10% of the hourly allowance. HTTP 429
  pauses upstream work for `Retry-After` or the known reset time, whichever is
  longer. Network/server errors back off. Stale data keeps its original date.
  Actual upstream work is additionally paced at one admission per second.
- One process and one persistent volume are supported. A file lock refuses a
  second worker on the same volume; do not horizontally scale this deployment.

Current defaults are tunable via the example environment file. The actual WCL
point allowance is learned from `rateLimitData`; an HTTP request is not assumed
to cost one point. Do not mass-prefetch unknown players. Keep cache retention
within WCL's applicable response headers/terms; this deployment is an on-demand
expiring cache, not a permanent data mirror.

## Operation and verification

The Docker volume stores cache, hashed sessions and quota counters. Back it up
privately; never upload it, `.env`, settings or credentials to GitHub/CurseForge.
Never remove the volume as a routine restart: that resets the local budget.

Set a long random `MPLUSLOGS_ADMIN_TOKEN` to enable `GET /metrics`, authenticated
with `Authorization: Bearer <admin token>`. The response contains counters for
upstream attempts, successful/negative cache hits, merged requests and upstream
errors, plus the last observed WCL point budget and pause time. It contains no
tokens, account IDs or character names. `/healthz` does not contact WCL.
Point deltas and the largest observed cost are conservative estimates: other
applications sharing the WCL quota may contribute to them. They are used to
avoid admitting a request that would consume the reserved point margin.

```sh
python -m unittest discover -s tests -p 'test_api_efficiency.py' -v
python -m unittest discover -s tests -p 'test_profile_server.py' -v
```

The tests use fake WCL responses and local HTTP sockets. Real WCL OAuth, quotas
and the Docker image require a configured deployment for end-to-end validation.

Upstream documentation:
- https://www.archon.gg/classic-vanilla/articles/help/api-documentation
- https://www.warcraftlogs.com/v2-api-docs/warcraft/ratelimitdata.doc.html
- https://www.archon.gg/fellowship/articles/news/api-updates-are-on-the-way
