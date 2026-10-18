## MPlusLogs 0.5.28 / Companion 1.0.21

- Load Mythic+ logs for members of listed groups, resolve missing realms through the Warcraft Logs API, and offer realm selection for ambiguous matches.
- Show loading stages and character or specialization progress in Companion.
- Preserve existing log-loading workflows when updating only the addon or Companion; use the leader profile when an older Companion does not support group discovery.
- Allow manual profile refresh after five minutes instead of incorrectly blocking it for an hour.
- Prevent crashes from incomplete realm identities, malformed Warcraft Logs or OAuth replies, and damaged cache or settings data; keep valid preferences and usable cached profiles.
- Keep batch imports usable when one character returns a long Unicode error, and negotiate structured error codes without changing legacy replies.
- Automatically clean old profile and search caches while preserving recent entries, settings, credentials and API budget state.
- Remove the Pause / Resume command from the Companion tray menu.
