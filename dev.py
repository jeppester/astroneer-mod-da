#!/usr/bin/env python3
"""Translate-and-see-it loop for the Astroneer Danish translation mod.

    ./dev.py                  watch and rebuild on every save (the default)
    ./dev.py --build-only     build once and exit, no watching
    ./dev.py --install        install the pak into the game after each build
    ./dev.py --clean          remove build/ and mod-output/, then exit
    ./dev.py --languages      print the game's language dropdown and exit

On start it regenerates workdir/Game_da.po from the game's own English
strings and applies translation/da.po (the source-controlled store) onto it, so
a git pull of someone else's translations shows up in the file you're about to
edit. Any edits already pending in Game_da.po are flushed into the store first,
so nothing is lost.

Then, on every save of Game_da.po: your edits go into da.po and the paks are
rebuilt. The two sync directions are deliberately not both live — only your
saves drive the loop, so nothing can bounce between the two files. To pull
translations mid-session, restart.

--install only takes effect on the game's NEXT launch: Unreal mounts paks at
startup and holds them while it runs. There's no live reload to be had — the
loop is save, build, install, relaunch.

Needs Astroneer installed; tools/gamefinder.py finds it across storefronts and
remembers where, so ASTRONEER_DIR is only needed to override that.
"""

import argparse
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

from tools import culture as culture_asset
from tools import translations
from tools.build import CULTURE_ASSET, Builder
from tools.console import Failure, detail, error, ok, say, warn
from tools.gamefinder import GameFinder

REPO_DIR = Path(__file__).resolve().parent
# The working PO lives outside translation/ on purpose: a PO editor writes a
# compiled Game_da.mo next to whatever file it saves, and that artifact has no
# business sitting beside the source-controlled store.
WORK_DIR = REPO_DIR / "workdir"
PO_FILE = WORK_DIR / "Game_da.po"
STORE_FILE = REPO_DIR / "translation" / "da.po"
SOURCE_LOCRES = "Astro/Content/Localization/Game/en/Game.locres"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--build-only", action="store_true",
                        help="build once and exit instead of watching for saves")
    parser.add_argument("--install", action="store_true",
                        help="copy a pak into the game's Paks directory after each build")
    parser.add_argument("--clean", action="store_true",
                        help="remove build/ and mod-output/ artifacts, then exit")
    parser.add_argument("--languages", action="store_true",
                        help="print the game's current language dropdown, then exit")
    parser.add_argument("--culture", default="da", help="culture code to build (default: %(default)s)")
    parser.add_argument("--display", default="Dansk",
                        help="label shown in the in-game language dropdown (default: %(default)s)")
    parser.add_argument("--interval", type=float, default=1.0, metavar="SECONDS",
                        help="how often to check for a save (default: %(default)s)")
    return parser.parse_args(argv)


def short(path):
    """A path as the user recognises it: relative to the repo when it's inside."""
    path = Path(path)
    try:
        return str(path.relative_to(REPO_DIR))
    except ValueError:
        return str(path)


def signature(path):
    """A content hash, so a touched-but-unchanged file doesn't trigger a build."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settle(path, interval=0.3):
    """Wait for a file to stop changing.

    A save can land in more than one write — an editor that writes in place is
    briefly half a file. This is about reading a whole file, not throttling.
    """
    current = signature(path)
    while True:
        time.sleep(interval)
        previous, current = current, signature(path)
        if current == previous:
            return current


def refresh_working_po(game):
    """Regenerate the working PO from the game, with the store applied."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if PO_FILE.exists() and translations.po_to_store(PO_FILE, STORE_FILE):
        ok(f"flushed pending edits in {PO_FILE.name} into {STORE_FILE.name}")
    total = translations.working_po_from_locres(game.read(SOURCE_LOCRES), PO_FILE)
    _, orphans = translations.store_to_po(PO_FILE, STORE_FILE)
    translated, _ = translations.progress(PO_FILE)
    ok(f"{PO_FILE.name}: {translated}/{total} translated ({translated / total * 100:.1f}%)")
    if orphans:
        warn(f"{orphans} translation(s) in {STORE_FILE.name} have no matching string "
             "in the game any more (removed upstream?) — left as-is")


def report(result, timestamp=False):
    stamp = f"{datetime.now():%H:%M:%S} " if timestamp else ""
    pct = (result.translated / result.total * 100) if result.total else 0.0
    ok(f"{stamp}built — {result.translated}/{result.total} entries translated ({pct:.1f}%), "
       f"{result.total - result.translated} fall back to English")
    for path, size in result.paks:
        detail(f"{short(path)} ({size / 1024:.0f}K)")
    if result.installed:
        detail(f"installed {result.installed.name} — relaunch the game to see it")


def main(argv=None):
    args = parse_args(argv)

    game = GameFinder(REPO_DIR).find()
    builder = Builder(REPO_DIR, game, args.culture, args.display)

    if args.clean:
        say("Cleaning build artifacts")
        ok(builder.clean())
        return 0

    if args.languages:
        uasset = game.read(f"{CULTURE_ASSET}.uasset")
        uexp = game.read(f"{CULTURE_ASSET}.uexp")
        say("Languages in the game's dropdown")
        for display, code in culture_asset.read_languages(uasset, uexp):
            detail(f"{display}  ->  {code}")
        return 0

    say(f"Reading source strings from {game.base_pak.name}")
    refresh_working_po(game)

    say(f"Building from {short(PO_FILE)}")
    report(builder.build(PO_FILE, install=args.install))

    if args.build_only:
        return 0

    print()
    say(f"Watching {short(PO_FILE)} — save to rebuild (ctrl-c to stop)")
    detail("Edit it in Poedit (https://poedit.net/) or any text editor.")
    if args.install:
        detail("Each rebuild is installed, but Unreal only picks a pak up at launch,")
        detail("so relaunch Astroneer to see a change.")

    last = signature(PO_FILE)
    while True:
        try:
            time.sleep(args.interval)
            current = signature(PO_FILE)
            if current == last:
                continue
            if current is None:
                warn(f"{PO_FILE.name} disappeared")
                last = current
                continue

            settle(PO_FILE)
            say(f"{PO_FILE.name} changed")
            if translations.po_to_store(PO_FILE, STORE_FILE):
                ok(f"flushed your edits into {STORE_FILE.name}")
            else:
                detail(f"no change to {STORE_FILE.name}")
            try:
                report(builder.build(PO_FILE, install=args.install, quiet=True),
                       timestamp=True)
            except Failure as exc:
                error(str(exc))
            last = signature(PO_FILE)
        except KeyboardInterrupt:
            print()
            say("Stopped.")
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failure as exc:
        error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
