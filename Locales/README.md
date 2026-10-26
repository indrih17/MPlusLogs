# MPlusLogs translations

The addon chooses the language using WoW's `GetLocale()`. Supported client
locales: enUS, enGB, ruRU, deDE, esES, esMX, frFR, itIT, ptBR, koKR, zhCN, zhTW.
enGB shares enUS. Unknown locales use English. English loads first; a missing
entry in another locale retains its English translation.

`catalog.json` contains the source keys. Existing keys are the original Russian
UI strings; the appearance editor uses English source keys. Keys must remain
unchanged. Each locale JSON maps these keys to text.
Generated Lua files are loaded by the TOC before the addon code.

The nine-step tutorial has separate authored translations in `Tutorial/*.lua`,
with Russian and English in `../TutorialSteps.lua`. It supports the same client
locales. Tutorial translations are loaded after `TutorialSteps.lua` and are not
generated from `catalog.json`; `tools/localize_addon.py apply` leaves them intact.
See `../docs/tutorial.md` for the guide's translation and validation workflow.

To contribute:

1. Edit values in your locale's JSON file; do not change the keys.
2. Preserve WoW color tags (`|c...`, `|r`), keyboard shortcuts, command names,
   leading/trailing spaces and newlines used by the existing UI.
3. Run `python tools/localize_addon.py apply` from the addon folder.
4. Run `python -m unittest discover -s tests -p test_localization.py`.
5. Check text wrapping and button labels in that language in WoW.

Russian retains the original authored UI. English has edited terminology.
Other locales started as Google Translate drafts with selected recruitment
and Mythic+ terms edited. They still need native-speaker review before a
public release; automated checks do not establish linguistic quality.

The 0.6.0 appearance editor has authored English and Russian copy. New appearance
keys in the other nine dictionaries currently retain explicit English fallback
text rather than unreviewed machine translation. Existing translated copy is
preserved. Dynamic descriptor labels (font roles and per-column controls) are
catalog entries too; add those exact labels when extending the schema.

`tools/review_locale_terms.py` records initial terminology edits. Do not rerun
it over contributor edits unless intentionally reapplying those defaults.
`tools/localize_addon.py translate` is an optional build tool that sends only
catalog strings to Google Translate. Players do not need it. The addon never
downloads translations at runtime.

Localization changes display text only. Character/realm names, `All specs`
filter identifiers, clipboard envelopes and SavedVariables records stay
unchanged. WCL-provided dungeon/season/spec names remain source data; known
generic labels such as `All specs` are translated when displayed. The Companion uses a separate offline catalog in tools/companion_locales and has
a language selector in Settings; it supports the same client languages.

`../DungeonNames.lua` resolves profile dungeon labels without modifying canonical
WCL names. It includes verified English/Russian names for the current rotation;
"Game language" can use the client's ChallengeMode API for other languages.
Unknown dungeons and unavailable translations retain the source English name.
