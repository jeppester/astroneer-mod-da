#!/usr/bin/env python3
"""Keep translation/da.json and translation/Game_da.po in sync.

translation/da.json is the source-controlled translation store: a plain
msgctxt -> msgstr map containing only text this project's translators wrote.
It has no English game strings in it, so it's safe to distribute.

translation/Game_da.po is a generated working copy (see tools/setup.sh) that
also carries the original English msgid text, needed to translate in Poedit
or any PO editor. It's gitignored and gets rebuilt from the game's own files.

Commands:
    to-store   read Game_da.po, write any non-empty msgstr into da.json
    to-po      read da.json, apply its msgstr values onto Game_da.po
    watch      poll both files and run whichever direction is needed
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import polib

REPO_DIR = Path(__file__).resolve().parent.parent
PO_FILE = REPO_DIR / "translation" / "Game_da.po"
STORE_FILE = REPO_DIR / "translation" / "da.json"


def load_store(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def dump_store(store):
    return json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def save_store(store, path):
    text = dump_store(store)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def po_to_store(po_path=PO_FILE, store_path=STORE_FILE):
    if not po_path.exists():
        return False
    po = polib.pofile(str(po_path))
    store = {e.msgctxt: e.msgstr for e in po if e.msgstr.strip()}
    return save_store(store, store_path)


def store_to_po(po_path=PO_FILE, store_path=STORE_FILE):
    if not po_path.exists():
        return False
    po = polib.pofile(str(po_path))
    store = load_store(store_path)
    changed = False
    unmatched = set(store)
    for e in po:
        translation = store.get(e.msgctxt, "")
        unmatched.discard(e.msgctxt)
        if e.msgstr != translation:
            e.msgstr = translation
            changed = True
    if changed:
        po.save(str(po_path))
    if unmatched:
        print(
            f"  note: {len(unmatched)} translation(s) in {store_path.name} have no "
            f"matching string in {po_path.name} (removed from the game?) — left as-is",
            file=sys.stderr,
        )
    return changed


def _sig(path):
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).digest()


def watch(interval=1.0):
    print(f"watching {PO_FILE} and {STORE_FILE} (ctrl-c to stop)")
    if po_to_store():
        print(f"  synced {PO_FILE.name} -> {STORE_FILE.name}")
    po_sig = _sig(PO_FILE)
    store_sig = _sig(STORE_FILE)
    try:
        while True:
            time.sleep(interval)
            if _sig(PO_FILE) != po_sig:
                if po_to_store():
                    print(f"  {PO_FILE.name} changed -> updated {STORE_FILE.name}")
                po_sig = _sig(PO_FILE)
                store_sig = _sig(STORE_FILE)
                continue
            if _sig(STORE_FILE) != store_sig:
                if store_to_po():
                    print(f"  {STORE_FILE.name} changed -> updated {PO_FILE.name}")
                store_sig = _sig(STORE_FILE)
                po_sig = _sig(PO_FILE)
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["to-store", "to-po", "watch"])
    args = parser.parse_args()

    if args.command == "to-store":
        po_to_store()
    elif args.command == "to-po":
        store_to_po()
    elif args.command == "watch":
        watch()


if __name__ == "__main__":
    main()
