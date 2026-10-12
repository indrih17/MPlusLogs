# MPlusLogs release workflow

The user explicitly authorized ongoing publication of completed changes to
`indrih17/MPlusLogs` and CurseForge project `1740700`, including the Companion.

After finishing a functional change, validate and publish without asking the
user to request an update again. Run `tools/publish_changes.py --summary` with
a concise English description of the actual behavior change. Repeat --summary
for multiple changelog bullets. Use `.build-venv/Scripts/python.exe` locally.
The publisher runs all tests, raises the patch version, snapshots allowlisted
sources, commits and pushes. GitHub Actions builds and publishes both platforms.
Do not publish while another chat is editing the same files. Inspect the diff
and the GitHub Actions result. Fix failed checks before claiming publication.
CurseForge moderation is a separate step.

Never publish tokens, secrets, settings, cache, local results, backups or build
environments. Use `tools/export_release_source.py`'s allowlist. The upload
credential is only in GitHub Actions secret `CF_API_TOKEN`; never print it.

The publishing checkout is `%LOCALAPPDATA%/MPlusLogsDevelopment/build-tools/repository`.
The publisher state and source snapshots are alongside it. An override can be
set with `MPLUSLOGS_DEVELOPMENT_HOME`, but it must be outside the WoW installation.
Never put Git repositories under the game directory: Battle.net attempts to
repair Git object's read-only attributes and can repeatedly initialize updates.
The live AddOns folder is separate: never check out remote files over another
chat's live edits. Old local `.build-tools` content was moved outside WoW;
do not recreate a repository there.
