# Code signing policy

MPlusLogs and MPlusLogs Companion are licensed under the MIT License. Bundled
third-party components retain their own licenses and notices.

## Current status

Official Companion downloads are currently unsigned. We are preparing an
application for the SignPath Foundation open-source program. Approval has not
been granted; this page does not claim that current binaries are signed.

If approved, the signing attribution will be:

Free code signing provided by [SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

## Responsibilities and release approval

- Maintainer, committer and reviewer: [indrih17](https://github.com/indrih17).
- Signing approver: [indrih17](https://github.com/indrih17).
- Contributions from other authors require maintainer review before merging.
- Repository and signing-service accounts must use multi-factor authentication.
- Each signing request requires manual approval by the signing approver.
- Only the project's own executable and installer, built from the public
  repository by GitHub Actions, are eligible for project signing. Upstream
  libraries keep their original signatures or remain unsigned.
- The installer and update manifest are published after signing, with checksums
  calculated from the final installer. Signed artifacts must not be modified.

These signing procedures are planned requirements, not a claim that integration
with SignPath is already active.

## Privacy policy

See the project's [Privacy policy](README.md#privacy-policy), including the
Warcraft Logs and GitHub services used by Companion.
