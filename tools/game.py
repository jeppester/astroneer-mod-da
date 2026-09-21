"""One Astroneer install, and the files read out of it.

A Game is a directory that really holds the game — gamefinder.py is what turns
a guess, a remembered path or an $ASTRONEER_DIR into one.
"""

from pathlib import Path

from . import repak
from .console import Failure, ok

_PAK_DIR = "Astro/Content/Paks"
_PREFERRED_PAK = "pakchunk0-WindowsNoEditor.pak"


def _base_pak(game_dir):
    """The pakchunk0 pak inside game_dir, or None if it isn't an install."""
    paks = Path(game_dir) / _PAK_DIR
    preferred = paks / _PREFERRED_PAK
    if preferred.is_file():
        return preferred
    # A storefront shipping a build cooked for another platform names the chunk
    # after that platform instead.
    return next(iter(sorted(paks.glob("pakchunk0-*.pak"))), None)


class Game:
    """One Astroneer install: where it sits on disk, and what's inside it.

    A Game only exists for a directory that really holds an install, so having
    one is proof there's something to build against.

    It is also why a rebuild is cheap. Every `repak get` re-parses the base
    pak's 46k-entry index, which costs ~50 ms a file, so in a long-running
    session the files are read once and held. The cache is keyed on the base
    pak's mtime, so a game update still invalidates it: the point of reading
    these fresh was never to re-read them per build, only to never ship a
    stale copy.
    """

    def __init__(self, game_dir):
        game_dir = Path(game_dir)
        base_pak = _base_pak(game_dir)
        if base_pak is None:
            raise Failure(f"no Astroneer install under {game_dir}")
        self.game_dir = game_dir
        self.base_pak = base_pak
        self._cache = {}
        self._stamp = None
        self._format = None

    @property
    def paks_dir(self):
        """Where the game mounts paks from — the install target for a mod."""
        return self.game_dir / _PAK_DIR

    def read(self, path):
        """One file out of the base pak, from cache when it's still valid."""
        self._check_current()
        if path not in self._cache:
            self._cache[path] = repak.get(self.base_pak, path)
        return self._cache[path]

    def try_read(self, path):
        """Like read, but None instead of raising when the file isn't there."""
        try:
            return self.read(path)
        except Failure:
            return None

    def pak_format(self):
        """(version, seed, matched) of the base pak."""
        self._check_current()
        if self._format is None:
            self._format = repak.format_of(self.base_pak)
        return self._format

    def _check_current(self):
        """Drop everything read before a game update landed."""
        stat = self.base_pak.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if self._stamp != stamp:
            if self._stamp is not None:
                ok("the base pak changed — re-reading the game files")
            self._cache.clear()
            self._format = None
            self._stamp = stamp
