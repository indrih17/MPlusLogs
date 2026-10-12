# MPlusLogs

Mythic+ Warcraft Logs DPS/HPS profiles for WoW group recruitment, with a Windows Companion.

## Install

Install the addon from [CurseForge](https://www.curseforge.com/wow/addons/mpluslogs).
Download the Windows Companion from [Releases](https://github.com/indrih17/MPlusLogs/releases/latest):
use the Setup exe or extract the complete portable ZIP. Windows 10/11 x64;
no separate Python installation is needed. The Companion UI currently uses Russian.

Sign in through Warcraft Logs in the Companion. In WoW, right-click an applicant
or open `/mpl`, request their M+ logs, press Ctrl+C, wait, then press Ctrl+V.
Use `/mpl demo` for a fictional preview without an account.

The addon supports eleven locales, player panels, recruitment tooltips,
dual DPS/HPS profiles, batch candidate loading, stale-data indicators and manual import.
Percentiles describe available Warcraft Logs runs. They do not measure tank survival.

## Privacy

The Companion sends only MPlusLogs request envelopes to Warcraft Logs.
Unrelated clipboard text is not transmitted. It does not read game memory or
automate gameplay. Login uses browser OAuth with PKCE; local tokens are protected
with Windows DPAPI. Startup with Windows or WoW Retail and response sounds are opt-in.
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
TOC-referenced addon files, excludes local logs/tokens/cache, and removes the
development character snapshot from the shipped addon. The source snapshot is
a development test fixture. Frozen resources are checked without account access.
Release binaries are currently unsigned.

Every push to `main` runs the Windows tests, builds the addon and Companion,
publishes GitHub Release assets and uploads the addon to CurseForge with changelog.
Direct source commits automatically raise the patch version if needed.
CurseForge moderation must still approve the upload.

For the live addon folder, `tools/publish_changes.py --summary "Describe change"`
runs tests, raises the patch version, writes CHANGELOG.md and pushes an allowlisted
snapshot. A Codex heartbeat checks finished local edits every 15 minutes.

See [LICENSE](LICENSE) for usage terms. Bundled third-party components retain their licenses.
