## Companion 1.0.31

- Report actual batch results instead of claiming failed profiles are ready, while preserving usable cached profiles.
- Use short failure-specific retry delays, honor API reset times, and recover immediately after a validated sign-in.
- Classify Warcraft Logs GraphQL failures safely and isolate character-specific errors without stopping the whole batch.
