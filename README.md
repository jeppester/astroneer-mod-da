# Astroneer Danish Translation Mod

One command does everything:

```
./dev.py                  # translate: rebuilds the mod on every save
./dev.py --build-only     # just build the paks and exit
./dev.py --install        # ...and install into the game after each build
```

## What's here
This mod's source never carries game files or the game's original English strings —
those are gitignored artifacts, read fresh from your local Astroneer install on
every start. The only thing checked in is the Danish text this project's
translators actually wrote:

- `translation/da.po` — **source of truth.** A gettext PO file mapping `msgctxt`
  (the namespace + string hash the game uses to look up a string) to the Danish
  text. Every entry has an **empty `msgid`**, so the file carries none of the
  game's English strings — safe to distribute and easy to review. Sorted by
  `msgctxt`, unwrapped, with fixed header metadata so a sync never churns the
  file. `msgfmt --check` validates it.

  It lists **every key the game has**, including untranslated ones, which simply
  have an empty `msgstr`. That puts the key set itself under version control:
  progress is measurable from this file alone, and a string disappearing from
  the game shows up in a diff. No English leaks, because an untranslated entry
  has both `msgid` and `msgstr` empty.

  PO is used here rather than JSON or YAML because it treats every string
  identically: the value is always quoted and a newline is always an explicit
  `\n`, so multi-line translations keep their line structure while no whitespace
  can ever sit at the end of a physical line, where an editor or pre-commit hook
  that trims line ends would silently eat it.

  It is generated — edit `workdir/Game_da.po` and let `dev.py` write this file.
  (Note the two are different files: `workdir/Game_da.po` is the gitignored
  working copy that carries the English source text; `da.po` is the committed
  store.)
- `dev.py` — the only entry point. See [The loop](#the-loop).
- `tools/` — the library it drives. All Python; `tools/repak/repak` is the one
  binary, used to read and write `.pak` files.
  - `gamefinder.py` finds your Astroneer install ([how](#finding-the-game))
  - `game.py` the install it found, and the cache that keeps a rebuild cheap
  - `translations.py` the two PO files and the `.locres` the game reads
  - `build.py` stages and packs the mod paks
  - `repak.py` the wrapper around the `repak` binary
  - `locmeta.py` adds our culture to the compiled-culture manifest
  - `culture.py` adds our language to the in-game dropdown
  - `console.py` terminal output

Gitignored, generated on demand:
- `workdir/` — the scratch directory for the editable working file. Kept out of
  `translation/` because a PO editor compiles a `Game_da.mo` next to whatever
  file it saves, and nothing generated belongs beside the committed store.
- `workdir/Game_da.po` — the editable working file (gettext `.po` format),
  regenerated from the game's own English strings + `da.po`. This is what you
  open in Poedit.
  - `msgctxt` = the same hash key as in `da.po` (do not touch).
  - `msgid` = original English text (do not touch — comes from the game, not from us).
  - `msgstr` = the Danish translation. Leave empty to fall back to English for that entry.
- `.astroneer-dir` — where `tools/gamefinder.py` found the game, so it only has to
  look once. Machine-specific, hence not committed.
- `build/` — the staged pak trees for a single build. Wiped at the start of every build.
- `mod-output/` — where the finished mod `.pak`s go.

Needs `python3` with `polib` and `pylocres` (`pip install --user polib pylocres`),
and Astroneer installed locally.

There are 4003 translated entries out of 6443 keys in `translation/da.po`.

## The loop
```
./dev.py
```
On start it regenerates `workdir/Game_da.po` from the game's own English
strings and applies `translation/da.po` onto it, so translations pulled from git
show up in the file you're about to edit. Edits already pending in `Game_da.po`
are flushed into the store first, so nothing is lost. Then it builds once, and
watches.

Every save of `Game_da.po` flushes your edits into `da.po` and rebuilds the
paks, in about **450 ms** — the process stays resident, so the interpreter, the
imports and the game files it reads are all paid for once at startup.

The two sync directions are deliberately not both live — only your saves drive
the loop, so nothing can bounce between the two files. To pull someone's
translations mid-session, restart.

`--install` only takes effect on the game's **next launch**: Unreal mounts paks
at startup and holds them while it runs, so there is no live reload to be had.
The loop is save, build, install, relaunch.

Other flags: `--build-only` builds once and exits, `--clean` removes the build
artifacts, `--languages` prints the game's current language dropdown,
`--interval` sets how often a save is checked for, and `--culture`/`--display`
build for a language other than Danish.

## Editing the translation
Open `workdir/Game_da.po` in a PO editor (e.g. [Poedit](https://poedit.net/), free) or any text editor.
Fill in `msgstr "..."` under each `msgid` with the Danish translation. Leave `msgstr ""` for strings you haven't gotten to yet — untranslated entries just won't be included in the compiled locres (falls back to English in-game).

Leave `./dev.py` running while you do; that's what puts your work into the
source-controlled `translation/da.po`.

## What a build does
It compiles the `.po` to a `.locres`, adds the culture to `Game.locmeta`, adds
Danish to the language dropdown, and packs everything with the same pak version
and path-hash seed as the base game pak.

It builds from the working `workdir/Game_da.po`, which carries the English
source text, so untranslated strings are compiled into the locres as English.

### The two paks
They are **alternatives — install one, not both.** Both carry the same
`Game.locres` and `Game.locmeta`, so installing both just leaves the game to pick
between two copies of the same files.

`mod-output/AstroneerDanish_P.pak` — the normal choice. Four files:
```
Astro/Content/Localization/Game/da/Game.locres            the translation
Astro/Content/Localization/Game/Game.locmeta              + "da" in the compiled-culture list
Astro/Content/Globals/LocalizationCultureOptions.uasset   + "Dansk" in the language dropdown
Astro/Content/Globals/LocalizationCultureOptions.uexp
```

`mod-output/AstroneerDanishTranslationOnly_P.pak` — the first two files only. It
overrides nothing that another language mod would also override, so the two can
be installed side by side. Without the dropdown entry, Danish can only be
selected with the `-culture=da` launch option.

The `_P` suffix gives a pak higher mount priority than `pakchunk0`, so its files shadow the base game's copies at runtime. Nothing in the game install is modified — deleting the pak restores stock behaviour.

Note that `repak pack` doesn't fix the order it stores files in, so two builds of
the same input can differ in which payload sits where. The index, the payloads
and the listing are identical; only the physical layout moves.

## Finding the game
`tools/gamefinder.py` tries, in order:

1. `$ASTRONEER_DIR`, if set. An override pointing somewhere without a game is an
   error rather than a reason to search elsewhere. It covers that one run and is
   deliberately not remembered, so a throwaway `ASTRONEER_DIR=... ./dev.py`
   can't quietly repoint the project.
2. `.astroneer-dir`, the answer a previous run remembered. If the game has since
   moved, this is reported and the search continues.
3. Every location a storefront is known to use — the Steam roots for each distro
   and packaging (native, Flatpak, Snap), **every library folder listed in that
   Steam install's `libraryfolders.vdf`** so a game on a second drive is found
   without being configured, removable and secondary drives, Epic via Heroic or
   a Wine prefix, and the Windows paths as WSL and git-bash see them (including
   the Microsoft Store's `XboxGames/<game>/Content` layout). Both the `ASTRONEER`
   and `Astroneer` spellings are tried, since stores differ.
4. Asking you to type or paste the path, when there's a terminal to ask on. A
   quoted, trailing-slashed, `~`-prefixed path works, as does one pointing *into*
   the install (the `Paks` folder or the `.pak` itself) — it's cut back to the
   root. Press enter to quit.

What 3 or 4 turn up is written to `.astroneer-dir`, so the search only happens
once. Delete that file to search again.

A location counts as an install if it holds `Astro/Content/Paks/pakchunk0-*.pak`.
The `-WindowsNoEditor` build is preferred; the glob is there so a store shipping
a differently-cooked chunk still resolves.

## The language dropdown
The list in Options > Language is *not* built by scanning the localization folders. It comes from one property in a cooked data asset, `Astro/Content/Globals/LocalizationCultureOptions`:

```
TMap<FString, FString> DisplayLanguageToCultureMapping    "ENGLISH" -> "en-US", "Deutsch" -> "de", ...
```

The map's strings are plain `FString`s baked into the asset, not locres entries, so they aren't translated per language — the menu shows every language in its own name. `tools/culture.py` appends `"Dansk" -> "da"` to that map, bumping the property's tag size plus the two byte counts in the `.uasset` header that depend on the `.uexp` length (the export's `SerialSize` and the package's `BulkDataStartOffset`). `./dev.py --languages` dumps the current map.

Because this is an override of a shipping asset, a game update that changes it would be shadowed by a stale copy. The same applies to `Game.locmeta`, the other shipping file this mod overrides. So both are read out of the installed base pak rather than kept in the repo, and nothing on disk survives a build. Within one `dev.py` session they are held in memory and reused — keyed on the base pak's mtime, so a game update still invalidates them. That is why a build needs the game present: there is deliberately nothing cached to fall back on. If the dropdown asset in particular can't be read out of the pak (the game moved it, say), `AstroneerDanish_P.pak` is skipped and any stale one deleted rather than shipping an outdated override; the translation-only pak still builds.

Without this patch the translation still works, but only via the `-culture=da` launch option.

## Notes
- Game install location: whatever `tools/gamefinder.py` resolves — on this machine `~/.local/share/Steam/steamapps/common/ASTRONEER`
- The base pak (`Astro/Content/Paks/pakchunk0-WindowsNoEditor.pak`, ~2.8GB) is NOT modified — we only read from it. This mod ships as a small separate override pak.
- No AES encryption on this pak, so no decryption key was needed.
