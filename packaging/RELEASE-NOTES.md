## MPlusLogs 0.5.29 / Companion 1.0.22

- **A major performance update for both MPlusLogs Companion and the addon, especially when loading logs for large applicant lists.**
- **Faster Companion:** character profiles load in parallel, ready group members start loading immediately, and concurrency adapts to your PC, connection and available Warcraft Logs quota.
- **Faster addon:** large clipboard replies use a lighter paste and import path, with fewer repeated text copies and shorter protocol lines to reduce processing overhead.
- **Less wasted work:** reuse valid cached profiles, resume interrupted realm searches and fetch the metrics you actually need. Additional DPS/HPS data loads when requested.
- **More reliable group logs:** keep same-name characters on different realms separate, preserve requested roles and specializations, and prevent renamed or transferred characters from appearing under the wrong identity.
- **More accurate statistics:** correct all-specs score totals and the key level/time associated with score runs while preserving Warcraft Logs data precision.
- **Stronger recovery:** fix crashes and stuck states caused by interrupted network replies, malformed data, locked result files, failed settings operations and damaged portable updates. Improve sign-in recovery and credential handling.
- **Thoroughly checked:** fix 21 confirmed issues and add 31 regression tests. The full 621-test suite completes without failures, with one optional Archon database check skipped. Both the installer and portable Companion builds pass their built-in checks.
- **Update both components** to get the complete performance and reliability improvements: MPlusLogs 0.5.29 and Companion 1.0.22.
