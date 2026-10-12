MPlusLogs Companion 0.5.0 for Windows 10/11 x64

Install using the Setup exe, or extract the entire portable ZIP to a permanent
folder and run MPlusLogs-Companion.exe. Python is included; no separate install
is needed. Keep all files in the portable folder together.

Install the WoW addon separately through CurseForge. Sign in to Warcraft Logs
in the Companion, then copy a request in WoW with Ctrl+C and paste the response
with Ctrl+V. The Companion interface currently uses Russian.

Only MPlusLogs request envelopes are sent to Warcraft Logs. Other clipboard
contents are not sent. The Companion does not read game memory or automate
gameplay. Optional startup settings are disabled by default.

Settings and DPAPI-protected login tokens are stored in:
%LOCALAPPDATA%\MPlusLogs\settings.json
The cache and most recent response are stored in the same directory.
Uninstall keeps these data. Sign out in the Companion to remove saved tokens.

This first release is not Authenticode-signed.
Source and releases: https://github.com/indrih17/MPlusLogs
