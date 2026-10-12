# Companion translations

The Companion supports the same languages as WoW: English (enUS/enGB), Russian,
German, Spanish (Spain and Latin America), French, Italian, Brazilian Portuguese,
Korean, Simplified Chinese and Traditional Chinese. The default follows Windows;
a manual choice is saved per user and applies without restarting.

JSON keys are the stable authored source strings. `enUS.json` is the reviewed
English reference; `ruRU.json` contains authored Russian. Other locale files
start from machine translation of the English reference with protected product
names, keyboard shortcuts and placeholders, followed by UI terminology edits.
Native-speaker contributions are welcome. No translation service runs in the app.

Edit locale JSON values without changing keys. Preserve `{code}`, newlines,
Ctrl+A/C/V and product names. Run `python -m unittest discover -s tests -q`.
`tools/localize_companion.py` is an optional build tool, not a player dependency.
Its `translate --force` command overwrites drafts; do not use it over reviewed
contributor translations. Packaged EXEs contain every locale.
