# MPlusLogs agent collaboration

Agents may independently spawn and delegate work to as many subagents as useful,
within the environment's available concurrency and resource limits, without
asking the user for permission. Subagents may delegate further under the same
rule. Choose the number and scope of agents to improve the quality of the result;
the user prioritizes thoughtful, well-founded work over minimizing agent count.

Give each agent a clear task and file ownership when edits run in parallel.
The coordinating agent remains responsible for reconciling findings, reviewing
the combined changes, resolving conflicts, and validating the complete result.

Keep track of every active delegated task until its result has been reviewed
and integrated or the user explicitly pauses or cancels it. Check progress and
results at meaningful intervals, address blockers, and follow up on unfinished
work. Delegating a task does not complete the coordinator's responsibility.

Treat additional user questions and side topics as part of the ongoing work
unless the user explicitly changes the objective. After handling them, return
to the main task and check the delegated work. Preserve the objective, pending
tasks, and next steps across turns and context compaction; report completion
only after the combined result has been validated.

# MPlusLogs release workflow

Ask for explicit user confirmation before each push or publication to
`indrih17/MPlusLogs` and CurseForge project `1740700`, including the Companion.
The user revoked the previous standing authorization to publish automatically.
Approval applies only to the presented changes, not to future releases.

After finishing a functional change, validate it, inspect the diff, summarize
the completed changes and checks, and ask whether to push and publish them.
Wait for confirmation before running the publisher: its push triggers releases.
After approval, run `tools/publish_changes.py --summary` with
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
