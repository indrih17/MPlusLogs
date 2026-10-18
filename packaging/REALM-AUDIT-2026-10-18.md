# Realm catalogue verification, 2026-10-18

Source: Warcraft Logs' authenticated read-only GraphQL API,
`https://www.warcraftlogs.com/api/v2/user`. No credentials or account details
are included in the accompanying public catalogue.

All 1,034 entries from the previous `realm-slugs.json` were submitted to
`worldData.server(region, slug)` in batches. 919 resolved; 115 were not
recognized by that endpoint. Unrecognized historical entries were preserved,
without inventing replacements. Every resolved entry returned its expected
region. 430 values were replaced with the API's canonical slug.

The full paginated `worldData.regions.servers` catalogue contained 938 servers:
US 247, EU 268, KR 23, TW 28, CN 372. All nonempty `name` and `normalizedName`
values were merged into the realm mapping. Seven CN entries had an empty
normalized name; empty strings are never registered as aliases. The public
snapshot is `packaging/realm-catalogue-audit.json`.

`tests/test_realm_localizations.py` checks every supplied nonempty name against
the mapping and every server against the ID-based verifier. This covers the
names supplied by WCL's current catalogue, not hypothetical translations or
future servers. New name-search API requests resolve the submitted realm with
`worldData.server` and compare its ID with `character.server.id` in the same
query. Different IDs reject the candidate even if its spelling matches.
Old cache records retain the strict legacy name/alias check until refreshed.

The live API accepted the localized `ревущии-фьорд` URL and returned ID 495
for both the requested realm and Газоваяфура's server (`howling-fjord`).

Separately, replaying actual cached API replies for Gauchosham, Zaratrass,
Filtráki and Rhynozeros imported four profiles through the real Lua parser;
each profile contained eight dungeons. This replay does not replace a live
browser search or an in-game visual check. CAPTCHA and incomplete WCL search
results remain external limits of the experimental browser-based discovery.
