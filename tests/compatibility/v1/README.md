# Frozen protocol compatibility fixtures

These are unmodified public sources from the local source snapshot captured
before the 2026-10-18 audit, when the addon declared 0.5.27 and Companion 1.0.20.
They are test data, never imported by the shipped applications or copied into
the addon archive. The tests execute them explicitly to check mixed-version
clipboard request parsing, profile/error import and group search.

Do not update these fixtures to make a compatibility test pass. Extend the
test matrix with another version when deliberately changing the protocol.
The frozen Companion envelope handler uses the current fetch adapter with
network replaced by synthetic fixtures; it preserves its original capability
validation, request recognition and legacy reply formatting.

The synthetic inputs contain no credentials or captured user profiles. The
sources retain their original project license (see the root LICENSE).
