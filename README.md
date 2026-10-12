# MPlusLogs

Mythic+ Warcraft Logs DPS/HPS profiles for WoW group recruitment, with a Windows Companion.

## Install

Install the addon from [CurseForge](https://www.curseforge.com/wow/addons/mpluslogs).
**REQUIRED: Install and run MPlusLogs Companion on Windows. Online log loading does not work without it.**
Download the Companion from [Releases](https://github.com/indrih17/MPlusLogs/releases/tag/companion-channel):
use the Setup exe or extract the complete portable ZIP. Windows 10/11 x64;
no separate Python installation is needed. The Companion supports all WoW client languages; select one in Settings > Language.

Sign in through Warcraft Logs in the Companion. In WoW, right-click an applicant
or open `/mpl`, request their M+ logs, press Ctrl+C, wait, then press Ctrl+V.
Use `/mpl demo` for a fictional preview without an account.

The addon supports eleven locales, player panels, recruitment tooltips,
dual DPS/HPS profiles, batch candidate loading, stale-data indicators and manual import.
DPS is shown first for every role, including healers; full profiles use Warcraft Logs-style tables with dungeon icons and DPS/HPS tabs. HPS also remains available in tooltips.
Customize healer HPS priority, Best avg/Median priority, freshness (6/12/24/48 hours),
tooltips and stale-log alerts in Settings > AddOns > MPlusLogs, or use `/mpl settings`.
Changes apply immediately and are saved between sessions.
Percentiles describe available Warcraft Logs runs. They do not measure tank survival.

## Privacy

The Companion sends only MPlusLogs request envelopes to Warcraft Logs.
Unrelated clipboard text is not transmitted. It does not read game memory or
automate gameplay. Login uses browser OAuth with PKCE; local tokens are protected
with Windows DPAPI. Startup with Windows or WoW Retail is optional. Response sounds are enabled by default and can be disabled in Settings.
Settings, tokens, cache and recent results are stored in `%LOCALAPPDATA%\MPlusLogs`.
Sign out to remove saved tokens; uninstall preserves local data.

## Build and test

Requires Python 3.12 on Windows with tkinter and Inno Setup 6.

```powershell
python -m pip install pyinstaller==6.22.0 lupa Pillow
python -m unittest discover -s tests -q
python tools/build_release.py --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

Output: `release-output/`, including SHA-256 checksums. The script packages only
TOC-referenced addon files and bundled dungeon icons, excludes local logs/tokens/cache, and removes the
development character snapshot from the shipped addon. The source snapshot is
a development test fixture. Frozen resources are checked without account access.
Release binaries are currently unsigned.

Companion starts its own version series at 1.0.0; the addon keeps its 0.x series. Each component advances only when its shipped files change. Companion-only releases do not create addon updates on CurseForge. Companion has an independent version. It checks for updates on startup and once a day, downloads a verified installer and offers an install-and-restart button. Settings, login and startup choices are preserved. Existing users must install this updater-enabled Companion once. Portable users can use the same update button; it installs into the current folder and registers the installation with Windows.

Every push to `main` runs the Windows tests and builds the addon. Companion binaries are built and released only when its shipped inputs change. The workflow
publishes GitHub Release assets and uploads the addon to CurseForge with changelog.
Direct source commits automatically raise the patch version if needed.
CurseForge moderation must still approve the upload.

For the live addon folder, `tools/publish_changes.py --summary "Describe change"`
runs tests, raises the patch version, writes CHANGELOG.md and pushes an allowlisted
snapshot. A Codex heartbeat checks finished local edits every 15 minutes.

See [LICENSE](LICENSE) for usage terms. Bundled third-party components retain their licenses.
