MPlusLogs Companion 1.0.32 for Windows 10/11 x64

Install using the Setup exe, or extract the entire portable ZIP to a permanent
folder and run MPlusLogs-Companion.exe. Python is included; no separate install
is needed. Keep all files in the portable folder together.

Companion may be installed in Interface\AddOns or its own separate folder.
Do not install it inside an individual addon folder, such as AddOns\MPlusLogs.
Setup rejects individual addon folders. A portable copy started inside an addon offers
to copy its program files to %LOCALAPPDATA%\Programs\MPlusLogs Companion
(or an unused numbered folder), update its own shortcuts and startup entries,
and restart. Login and settings stay in the per-user data directory. Declining
closes Companion. Old files are kept; remove only the old Companion payload
after it exits, without deleting addon files.
For an older Companion already inside an addon folder, exit it from the tray and run
the latest Setup in the recommended folder; older versions cannot relocate
themselves through their built-in updater.

Install the WoW addon separately through CurseForge. Sign in to Warcraft Logs
in the Companion, then copy a request in WoW with Ctrl+C and paste the response
with Ctrl+V. Choose the interface language in Settings > Language. The default follows Windows.

Only MPlusLogs request envelopes are sent to Warcraft Logs. Other clipboard
contents are not sent. The Companion does not read game memory or automate
gameplay. Optional startup settings are disabled by default.

Replies are marked to stay out of Windows clipboard history and cloud sync.
When Windows permits history access, Companion removes only exact copies of
requests it has processed. Other history entries are preserved; history text
is not logged or transmitted. This does not clear older, unprocessed requests.

Settings and DPAPI-protected login tokens are stored in:
%LOCALAPPDATA%\MPlusLogs\settings.json
The cache and most recent response are stored in the same directory.
Uninstall keeps these data. Sign out in the Companion to remove saved tokens.

This first release is not Authenticode-signed.
Source and releases: https://github.com/indrih17/MPlusLogs

Companion updates independently of the addon. Updates are checked on startup
and daily. Use Install update and restart, or Settings > Check Companion updates.
Login, settings and startup preferences are preserved. Portable updates download
a verified ZIP, close Companion, replace only its program files in the same
folder, and restart. A failed replacement or self-test restores the previous
files. Portable updates do not run Setup or register an installed application.
Logs and the last update result are stored in the per-user data directory.
