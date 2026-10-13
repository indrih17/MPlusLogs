# Changelog

## MPlusLogs 0.5.13 / Companion 1.0.6

- Reuse the same account-isolated profile cache after OAuth token refreshes and signing back into Warcraft Logs.
- Show logs for the selected group dungeon and preserve separate specialization profiles with automatic and manual selection.

## Release tooling

- Record the submitted SignPath Foundation application while accurately marking current downloads as unsigned pending review.

## MPlusLogs 0.5.12 / Companion 1.0.5

- License MPlusLogs and Companion under MIT and document the planned code signing policy and network privacy behavior.

## Companion 1.0.5

- Remove the optional hosted profile server, Docker deployment files and service login; Companion connects directly to WCL with personal or shared API clients.

## Companion 1.0.5

- Hide the Back button on the first personal API setup step and retain navigation on subsequent steps.

## Companion 1.0.5

- Fix unreadable personal API setup fields and blank white scrolling areas in dark theme.
- Publish only the Companion installer in user-facing releases and keep update metadata in the service channel.

## MPlusLogs 0.5.12 / Companion 1.0.5

- Add an illustrated three-step personal WCL API setup and migration prompt for shared-client users.
- Show each selected WCL client's quota reset countdown and recommend personal API when the shared allowance is exhausted.

## Companion 1.0.4

- Fix installer startup with existing Windows or WoW Retail autostart settings by reading the selected directory before the app constant is initialized.

## Companion 1.0.3

- Limit each verified account to a configurable share of the shared WCL point budget, in addition to hourly and daily profile-load limits.
- Close failed upstream HTTP responses promptly and include the reported retry delay in rate-limit messages.

## Companion 1.0.2

- Reuse dual DPS/HPS profiles across roles for 24 hours and cache valid missing-log responses for six hours.
- Persist API budgets and refresh cooldowns across restarts, pace upstream requests and stop batches after rate-limit failures while preserving dated cached data.
- Add an optional Docker public-profile service with verified-account quotas, a shared cache, deduplicated requests, a fair queue and HTTPS deployment configuration.
- Verify installer exit status and the installed Companion version, preserve installation diagnostics and prevent automatic retries of failed updates.

## Companion 1.0.1

- Show the installed Companion version explicitly in the main window and settings, translated into the selected interface language.

## Companion 1.0.0

- Start the independent Companion 1.x version series and publish only components whose shipped files changed; Companion-only releases no longer update the addon or CurseForge.
- Keep release notes focused on changes and remove the repeated Companion installation boilerplate.

## 0.5.11

- Release Companion independently with background update checks, verified downloads and one-click install and restart while preserving login and startup preferences.
- Show a one-time Companion updater installation notice in the addon and support capability checks without disrupting compatible older Companions.

## 0.5.10

- Show an explicit three-way Companion startup choice in setup and settings
- Handle WCL throughput response variants and show actionable log-loading error guidance

## 0.5.9

- Clearly require MPlusLogs Companion for online log loading

## 0.5.8

- Show the MPlusLogs logo in the WoW addon list.

## 0.5.7

- Redesign the full profile table to match Warcraft Logs with score summary, grouped columns, dungeon icons and DPS/HPS tabs.
- Preserve applicant context when switching metrics and show dashes for unavailable metric-specific time and rank fields.

## 0.5.6

- Keep publishing metadata outside WoW, reject development files in addon archives, and support Windows short-path aliases in release checks.

## 0.5.5

- Keep local publishing Git metadata and source snapshots outside the WoW installation to avoid Battle.net permission-repair loops.
- Reject hidden Git metadata and development folders in addon release archives and CurseForge uploads.

## 0.5.4

- Add native WoW addon settings for healer HPS priority, Best avg or Median priority, log freshness, tooltips and stale-log alerts.
- Apply saved display preferences immediately to applicant rows, profiles and tooltips without reloading log data.

## 0.5.3

- Show DPS first for all roles, including healers, in applicant rows, profiles and tooltips; keep HPS as the secondary metric.
- Refresh legacy HPS-only profiles during batch loading when DPS data is missing.

## 0.5.2

- Add Companion translations for all WoW client languages with a saved language selector and Windows language detection.
- Enable the ready-reply sound by default for new settings while preserving saved sound preferences.

## 0.5.1

- Batch loading skips profiles updated within the last 24 hours; 30 fresh applicants plus 5 new applicants now requests only the 5 new profiles.
- Disable batch loading when every candidate has fresh data, while keeping individual manual refresh available.
- Automatically build and publish addon and Windows Companion updates to GitHub and CurseForge with versioned changelogs.

## 0.5.0

- First public release: Mythic+ Warcraft Logs profiles, recruitment tooltips, batch loading and eleven addon locales.
- Windows Companion installer and portable ZIP with browser sign-in, tray and optional startup.
