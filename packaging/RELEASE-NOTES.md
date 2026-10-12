## Companion 1.0.2

- Reuse dual DPS/HPS profiles across roles for 24 hours and cache valid missing-log responses for six hours.
- Persist API budgets and refresh cooldowns across restarts, pace upstream requests and stop batches after rate-limit failures while preserving dated cached data.
- Add an optional Docker public-profile service with verified-account quotas, a shared cache, deduplicated requests, a fair queue and HTTPS deployment configuration.
- Verify installer exit status and the installed Companion version, preserve installation diagnostics and prevent automatic retries of failed updates.
