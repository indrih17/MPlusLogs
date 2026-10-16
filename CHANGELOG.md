# Changelog

## MPlusLogs 0.5.25 / Companion 1.0.17

- Show current specialization, WCL specialization ranks and dungeon score specialization icons in player profiles.
- Add dungeon-specific WCL links and BlizzMove profile window scaling support.
- Keep result colors for stale profiles and show a separate warning with the last download date; improve player tabs and download error messages.
- Respect the five-minute profile refresh interval in the addon and refresh only eligible group profiles.
- Explain primary statistic choices in settings and update interface translations.
- Organize Companion settings, fix dark-theme control colors and restrict no-WCL diagnostics to development launches.

## MPlusLogs 0.5.24

- Add All Specs to the profile selector and use it by default, preserving explicit specialization choices.
- Keep the aggregate Warcraft Logs profile selected after loading specialization history.

## Release tooling

- Update the bilingual CurseForge description with portable downloads, Companion updates, installation folders and manual log refresh timing.

## Companion 1.0.16

- Refresh explicitly requested M+ profiles from Warcraft Logs after a five-minute per-profile cache interval; retain cached data and its original date on API failures.
- Refresh the currently selected party specialization, preserve pending requests when no download is needed, and offer targeted loading of additional specializations.
- Match all seven Warcraft Logs percentile colors, including gold for 100.
- Publish a portable ZIP alongside the recommended installer, with separate verified ZIP updates, canonical Windows path handling, runtime self-tests and rollback; document both downloads in English and Russian.

## MPlusLogs 0.5.23 / Companion 1.0.15

- Refresh explicitly requested M+ profiles from Warcraft Logs after a five-minute per-profile cache interval; retain cached data and its original date on API failures.
- Refresh the currently selected party specialization, preserve pending requests when no download is needed, and offer targeted loading of additional specializations.
- Match all seven Warcraft Logs percentile colors, including gold for 100.
- Publish a portable ZIP alongside the recommended installer, with separate verified ZIP updates, runtime self-tests and rollback; document both downloads in English and Russian.

## Companion 1.0.14

- Allow installing and running Companion directly in Interface\AddOns or a separate folder alongside addons; protect individual addon folders from Companion file locks.

## Companion 1.0.13

- Allow choosing a new Companion installation folder when reinstalling, including when addon updates removed the previous installation but left its Windows registration.

## MPlusLogs 0.5.22

- Prefix dungeon-specific tooltip rows with bracketed dungeon abbreviations and remove the source/date row.
- Open all party profiles from a party member menu while keeping the clicked member selected.
- Preserve the full party when loading logs from player tabs or stale-data notices.
- Add a Main specialization setting: current group/applicant specialization by default, or saved WCL history.

## Companion 1.0.12

- Treat empty Warcraft Logs throughput arrays as absent measurements instead of rejecting the response format.
- Show the normal no-public-logs state for leaderboard-only results and preserve available DPS or HPS when the other metric is absent.

## MPlusLogs 0.5.21

- Keep Mythic+ logs always enabled in M+ groups and add independent opt-in settings for raids, PvP, and all other groups.
- Group the content visibility checkboxes in a separate section at the bottom of addon settings and apply them to log columns, tooltips, menus, and batch downloads.

## MPlusLogs 0.5.20

- Disable Load all logs for raid listings and recheck the listing before starting a batch request.

## Companion 1.0.11

- Remove the local combat history preview and analysis from Companion.
- Link directly to the current Companion installer in download instructions.

## MPlusLogs 0.5.19

- Open party members' logs in tabs, including group applicants, with one batch refresh for missing or stale profiles.

## MPlusLogs 0.5.18 / Companion 1.0.10

- Compare canonical Windows executable paths when relocating Companion so startup entries and shortcuts using short names or junctions are updated correctly.

## Companion 1.0.9

- Preserve bundled realm lookup data and license notices when relocating Companion outside AddOns; verify relocation support in the frozen build.

## Companion 1.0.8

- Prevent Companion installation inside WoW AddOns, including linked folders.
- Offer safe relocation of portable Companion copies from AddOns, preserving login, settings, startup entries and shortcuts while releasing old executable locks.

## MPlusLogs 0.5.17

- Add current-dungeon numeric DPS/HPS, Median and Best choices to the primary statistic setting for applicant rows, profile summaries and tooltips, honoring the healer HPS-first preference and keeping missing dungeon data unavailable.

## MPlusLogs 0.5.16 / Companion 1.0.7

- Load separate Warcraft Logs specialization profiles and show only logged specializations in the selector; hide the dropdown when only one is available.
- Show normal empty profile states for hidden or absent logs, preserve confirmed privacy status, and distinguish delayed requests from unavailable logs.
- Add local combat-log history with per-run party utility counters and Companion-to-addon history import.
- Improve Companion table and theme styling and verify installer updates before reporting success.

## MPlusLogs 0.5.15

- Declare compatibility with WoW 12.1.5 while retaining support for 12.0.7 and 12.1.0.

## MPlusLogs 0.5.14

- Remove the unconditional Companion update prompt and misleading receive-response button.
- Select the full clipboard request for Ctrl+C and Ctrl+V, and require Ctrl+C before advancing the copy step.

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
