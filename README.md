# Astroneer Danish Translation Mod

A Danish translation of Astroneer, shipped as an override pak. The game install
is never modified, and the repo holds only the Danish text: `translation/da.po`
maps each of the game's string keys to its translation, without the English
originals. Those are read from your local install when you run the project.

## Running it

Needs `python3` with `polib` and `pylocres`, and Astroneer installed locally:

```
pip install --user polib pylocres
./dev.py
```

`dev.py` finds the game, generates `workdir/Game_da.po` (with the English text
alongside the translations), builds the mod into `mod-output/`, and rebuilds on
every save. Open `workdir/Game_da.po` in [Poedit](https://poedit.net/) or any
text editor and fill in `msgstr` for each string. Leave `dev.py` running, as it
writes your edits back into `translation/da.po`.

```
./dev.py --install        # also install the pak into the game after each build
./dev.py --build-only     # build once and exit
./dev.py --help           # all options
```

The game picks up a new pak on its next launch.
