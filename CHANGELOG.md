# Changelog

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
