# Astroneer Danish Translation Mod

## What's here
This mod's source never carries game files or the game's original English strings —
those are gitignored artifacts, pulled fresh from your local Astroneer install by
`tools/setup.sh`. The only thing checked in is the Danish text this project's
translators actually wrote:

- `translation/da.json` — **source of truth.** A plain `msgctxt -> Danish text` map
  (`msgctxt` is the namespace + string hash the game uses to look up the string).
  No English text, no game data — safe to distribute and easy to review/diff.
- `tools/setup.sh` — one-time (re-runnable) setup. Extracts the game's English
  strings and the language-dropdown asset from your local install, then generates
  `translation/Game_da.po` from them with `translation/da.json`'s translations
  merged in.
- `tools/sync-translations.py` / `tools/watch-translations.sh` — keep `Game_da.po`
  and `da.json` in sync as you translate (see below).
- `tools/repak/repak` — CLI tool for reading/writing Unreal Engine `.pak` files (no install needed, just run it).
- `tools/patch-culture-options.py` — appends a language to the dropdown asset.

Gitignored, generated on demand:
- `source-locres/en/Game.locres`, `source-locres/Game.locmeta` — the game's own
  English strings, extracted by `tools/setup.sh`.
- `source-assets/Astro/Content/Globals/LocalizationCultureOptions.uasset`/`.uexp` —
  untouched copies of the cooked asset that holds the in-game language dropdown
  (see below), extracted by `tools/setup.sh`. `build.sh` re-extracts them on every
  build too, and warns if a game update has changed them since `setup.sh` last ran.
- `translation/Game_da.po` — the editable working file (gettext `.po` format),
  regenerated from `source-locres` + `da.json`. This is what you open in Poedit.
  - `msgctxt` = the same hash key as in `da.json` (do not touch).
  - `msgid` = original English text (do not touch — comes from the game, not from us).
  - `msgstr` = the Danish translation. Leave empty to fall back to English for that entry.
- `mod-output/` — where the finished mod `.pak` will go.

## One-time setup
```
./tools/setup.sh
```
Requires Astroneer to be installed locally (set `ASTRONEER_DIR` if it's not at the
default Steam path). This extracts the game files above and writes
`translation/Game_da.po`. Re-run it any time the game updates and you want fresh
source strings — it flushes any pending edits in the current `Game_da.po` into
`translation/da.json` first, so nothing gets lost.

There are 4006 translated entries in `translation/da.json`.

## Editing the translation
Open `translation/Game_da.po` in a PO editor (e.g. [Poedit](https://poedit.net/), free) or any text editor.
Fill in `msgstr "..."` under each `msgid` with the Danish translation. Leave `msgstr ""` for strings you haven't gotten to yet — untranslated entries just won't be included in the compiled locres (falls back to English in-game).

While you work, run this in the background (or in a spare terminal) so your edits
land in the source-controlled `translation/da.json` as you save, and so a `git pull`
that brings in new translations gets applied back onto your open `Game_da.po`:
```
./tools/watch-translations.sh
```

## Building the mod (once translation is in progress)
```
./build.sh              # -> mod-output/AstroneerDanish_P.pak
./build.sh --install    # ...and copy it into the game's Paks directory
```
It compiles the `.po` to a `.locres` (needs `pylocres` + `polib`), patches the culture into `Game.locmeta`, patches Danish into the language dropdown, and packs everything with the same pak version and path-hash seed as the base game pak.

The resulting pak contains four files:
```
Astro/Content/Localization/Game/da/Game.locres            the translation
Astro/Content/Localization/Game/Game.locmeta              + "da" in the compiled-culture list
Astro/Content/Globals/LocalizationCultureOptions.uasset   + "Dansk" in the language dropdown
Astro/Content/Globals/LocalizationCultureOptions.uexp
```
The `_P` suffix gives the pak a higher mount priority than `pakchunk0`, so those last three files shadow the base game's copies at runtime. Nothing in the game install is modified — deleting the pak restores stock behaviour.

## The language dropdown
The list in Options > Language is *not* built by scanning the localization folders. It comes from one property in a cooked data asset, `Astro/Content/Globals/LocalizationCultureOptions`:

```
TMap<FString, FString> DisplayLanguageToCultureMapping    "ENGLISH" -> "en-US", "Deutsch" -> "de", ...
```

The map's strings are plain `FString`s baked into the asset, not locres entries, so they aren't translated per language — the menu shows every language in its own name. `tools/patch-culture-options.py` appends `"Dansk" -> "da"` to that map, bumping the property's tag size plus the two byte counts in the `.uasset` header that depend on the `.uexp` length (the export's `SerialSize` and the package's `BulkDataStartOffset`). Run it with `--list` to dump the current map.

Because this is an override of a shipping asset, a game update that changes it would be shadowed by our stale copy. To keep that from going unnoticed, `build.sh` re-extracts the asset from the installed base pak on every build and warns when it differs from the vendored copy in `source-assets/`.

Without this patch the translation still works, but only via the `-culture=da` launch option.

## Notes
- Game install location: `~/.local/share/Steam/steamapps/common/ASTRONEER`
- The base pak (`Astro/Content/Paks/pakchunk0-WindowsNoEditor.pak`, ~2.8GB) is NOT modified — we only read from it. This mod ships as a small separate override pak.
- No AES encryption on this pak, so no decryption key was needed.
