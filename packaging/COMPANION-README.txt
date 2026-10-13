MPlusLogs Companion 1.0.8 for Windows 10/11 x64

Install using the Setup exe, or extract the entire portable ZIP to a permanent
folder and run MPlusLogs-Companion.exe. Python is included; no separate install
is needed. Keep all files in the portable folder together.

Keep Companion outside WoW Interface\AddOns so it cannot block addon updates.
Setup rejects AddOns destinations. A portable copy started from AddOns offers
to copy its program files to %LOCALAPPDATA%\Programs\MPlusLogs Companion
(or an unused numbered folder), update its own shortcuts and startup entries,
and restart. Login and settings stay in the per-user data directory. Declining
closes Companion. Old files are kept; remove only the old Companion payload
after it exits, without deleting addon files.
For an older Companion already inside AddOns, exit it from the tray and run
the latest Setup in the recommended folder; older versions cannot relocate
themselves through their built-in updater.

Install the WoW addon separately through CurseForge. Sign in to Warcraft Logs
in the Companion, then copy a request in WoW with Ctrl+C and paste the response
with Ctrl+V. Choose the interface language in Settings > Language. The default follows Windows.

Only MPlusLogs request envelopes are sent to Warcraft Logs. Other clipboard
contents are not sent. The Companion does not read game memory or automate
gameplay. Optional startup settings are disabled by default.

Settings and DPAPI-protected login tokens are stored in:
%LOCALAPPDATA%\MPlusLogs\settings.json
The cache and most recent response are stored in the same directory.
Uninstall keeps these data. Sign out in the Companion to remove saved tokens.

This first release is not Authenticode-signed.
Source and releases: https://github.com/indrih17/MPlusLogs

Companion updates independently of the addon. Updates are checked on startup
and daily. Use Install update and restart, or Settings > Check Companion updates.
Login, settings and startup preferences are preserved. Portable updates install
into the current folder and register the installation with Windows.
