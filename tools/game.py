"""One Astroneer install and the files read out of it."""

from pathlib import Path

from . import repak
from .console import Failure, ok

_PAK_DIR = "Astro/Content/Paks"
_PREFERRED_PAK = "pakchunk0-WindowsNoEditor.pak"


def _base_pak(game_dir):
    paks = Path(game_dir) / _PAK_DIR
    preferred = paks / _PREFERRED_PAK
    if preferred.is_file():
        return preferred
    # Other storefronts name the chunk after their platform.
    return next(iter(sorted(paks.glob("pakchunk0-*.pak"))), None)


class Game:
    """A directory that really holds an install, or construction fails.

    Files are cached because every `repak get` re-parses the base pak's index
    (~50 ms); the cache is keyed on the pak's mtime so a game update drops it.
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
        """Install target for a mod."""
        return self.game_dir / _PAK_DIR

    def read(self, path):
        self._check_current()
        if path not in self._cache:
            self._cache[path] = repak.get(self.base_pak, path)
        return self._cache[path]

    def try_read(self, path):
        """Like read, but None if the file isn't there."""
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
        stat = self.base_pak.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if self._stamp != stamp:
            if self._stamp is not None:
                ok("the base pak changed — re-reading the game files")
            self._cache.clear()
            self._format = None
            self._stamp = stamp
