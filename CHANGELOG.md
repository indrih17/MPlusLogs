# Changelog

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
