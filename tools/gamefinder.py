"""Find the local Astroneer install.

GameFinder(repo_dir).find() returns the Game — the install root, the folder
that contains Astro/ — looking in this order:

  1. $ASTRONEER_DIR. An explicit override pointing at the wrong place is an
     error, not a reason to go hunting somewhere else. It covers the one run
     only and is deliberately NOT remembered, so a throwaway
     `ASTRONEER_DIR=... ./dev.py` can't quietly repoint the project.
  2. .astroneer-dir, the answer a previous run remembered.
  3. Every place a storefront is known to install it, including each Steam
     library folder listed in libraryfolders.vdf, so a game on a second drive
     is found without being configured.
  4. Asking, when there's a terminal to ask on.

What 3 or 4 turn up is written to .astroneer-dir (gitignored), so the search
happens once. Delete that file to search again.
"""

import glob
import os
import re
from pathlib import Path

from .console import Failure, ok, say, warn
from .game import Game

CACHE_NAME = ".astroneer-dir"

_CACHE_HEADER = (
    "# Where this project found your Astroneer install. Generated, gitignored.\n"
    "# Delete this file to search again, or set ASTRONEER_DIR to override it.\n"
)

# Steam's root moves around by distro and packaging.
_STEAM_ROOTS = (
    "~/.local/share/Steam",
    "~/.steam/steam",
    "~/.steam/root",
    "~/.steam/debian-installation",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
    "~/snap/steam/common/.local/share/Steam",
    "/usr/local/share/Steam",
    "/usr/share/steam",
)

# Removable and secondary drives, where a library often sits before Steam has
# been told about it. Globs; unmatched patterns simply contribute nothing.
_STEAM_LIBRARY_GLOBS = (
    "/run/media/*/SteamLibrary",
    "/run/media/*/*/SteamLibrary",
    "/media/*/*/SteamLibrary",
    "/mnt/*/SteamLibrary",
)

# Steam installs to ASTRONEER, the Epic build to Astroneer; both are tried
# everywhere rather than guessing which store a path belongs to.
_GAME_DIR_NAMES = ("ASTRONEER", "Astroneer")

_OTHER_LOCATIONS = (
    # Epic, through Heroic or a Wine prefix.
    "~/Games/Heroic/{name}",
    "~/Games/{name}",
    "~/.wine/drive_c/Program Files/Epic Games/{name}",
    "~/Games/epic-games-store/drive_c/Program Files/Epic Games/{name}",
    # Steam's own Windows build under Wine.
    "~/.wine/drive_c/Program Files (x86)/Steam/steamapps/common/{name}",
    # Windows drives as WSL and as MSYS/git-bash see them. The Microsoft Store
    # layout nests the game one level down, in Content/.
    "/mnt/*/Program Files/Epic Games/{name}",
    "/mnt/*/Program Files (x86)/Steam/steamapps/common/{name}",
    "/mnt/*/XboxGames/{name}/Content",
    "/[a-z]/Program Files/Epic Games/{name}",
    "/[a-z]/Program Files (x86)/Steam/steamapps/common/{name}",
    "/[a-z]/XboxGames/{name}/Content",
)


def _steam_libraries():
    libraries = []
    for root in _STEAM_ROOTS:
        root = Path(root).expanduser()
        libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        # Each root can point at further library folders on other drives.
        text = vdf.read_text(encoding="utf-8")
        libraries += [Path(p) for p in re.findall(r'"path"\s*"([^"]+)"', text)]
    for pattern in _STEAM_LIBRARY_GLOBS:
        libraries += [Path(p) for p in glob.glob(pattern)]
    return libraries


def candidates():
    """Every place the game is known to land. Cheap: a couple of stats each."""
    found = []
    libraries = _steam_libraries()
    for name in _GAME_DIR_NAMES:
        for library in libraries:
            found.append(library / "steamapps" / "common" / name)
        for pattern in _OTHER_LOCATIONS:
            pattern = os.path.expanduser(pattern.format(name=name))
            if any(ch in pattern for ch in "*?["):
                found += [Path(p) for p in glob.glob(pattern)]
            else:
                found.append(Path(pattern))
    return found


class GameFinder:
    """Finds the install and remembers where it was, so the search runs once."""

    def __init__(self, repo_dir):
        self.cache = Path(repo_dir) / CACHE_NAME

    def find(self):
        """The installed Game. Raises Failure if there's nothing to build against."""
        override = os.environ.get("ASTRONEER_DIR")
        if override:
            game = self._open(override)
            if game is None:
                raise Failure(
                    f"ASTRONEER_DIR points at {override}, which holds no Astroneer install"
                )
            ok(f"Astroneer at {game.game_dir} (from ASTRONEER_DIR, this run only)")
            return game

        remembered = self._remembered()
        if remembered:
            game = self._open(remembered)
            if game:
                ok(f"Astroneer at {game.game_dir} (remembered)")
                return game
            warn(f"{self.cache.name} points at {remembered}, which is gone — looking again")

        say("Looking for your Astroneer install")
        for candidate in candidates():
            game = self._open(candidate)
            if game:
                ok(f"Astroneer at {game.game_dir} (found)")
                self._remember(game.game_dir)
                return game

        game = self._ask()
        if game:
            return game
        raise Failure(
            "no Astroneer install to build against — set ASTRONEER_DIR to point at one"
        )

    def _open(self, game_dir):
        """A Game for game_dir, or None when it isn't an install."""
        try:
            return Game(game_dir)
        except Failure:
            return None

    def _remembered(self):
        if not self.cache.is_file():
            return None
        for line in self.cache.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                return Path(line)
        return None

    def _remember(self, game_dir):
        text = f"{_CACHE_HEADER}{game_dir}\n"
        if self.cache.is_file() and self.cache.read_text(encoding="utf-8") == text:
            return
        self.cache.write_text(text, encoding="utf-8")
        ok(f"remembered it in {self.cache.name}")

    def _ask(self):
        """Let the user point at the install. Returns a Game, or None to give up."""
        if not os.isatty(0):
            return None
        print()
        print("  Astroneer isn't in any of the usual places. Type or paste the install")
        print("  folder — the one that contains Astro/ — or press enter to give up.")
        while True:
            try:
                reply = input("  path: ")
            except EOFError:
                print()
                return None
            if not reply:
                return None
            game = self._open(reply)
            if game:
                ok(f"Astroneer at {game.game_dir} (you told us)")
                self._remember(game.game_dir)
                return game
            warn(f"no Astroneer install under {reply}")
