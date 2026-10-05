"""Translation store and working copy.

translation/da.po is the source-controlled store: msgctxt -> msgstr for every
key the game has, translated or not. All msgids are empty, so it carries none
of the game's English text. The game looks strings up by msgctxt, so msgid
isn't needed to identify an entry.

translation/Game_da.po is the gitignored working copy with the English msgids,
rebuilt from the game's files on every start, for editing in a PO editor.
"""

from dataclasses import dataclass

import polib
from pylocres import Entry, LocresFile, LocresVersion, Namespace

# 3 = CityHash
LOCRES_VERSION = 3

# No dates: they would rewrite the store on every sync.
STORE_METADATA = {
    "Project-Id-Version": "astroneer-mod-da",
    "Language": "da",
    "MIME-Version": "1.0",
    "Content-Type": "text/plain; charset=UTF-8",
    "Content-Transfer-Encoding": "8bit",
}


def working_po_from_locres(locres_bytes, po_path):
    """Write the editable working PO from the game's own English locres."""
    locres = LocresFile()
    locres.read(locres_bytes)
    po = polib.POFile()
    for namespace in locres:
        for entry in namespace:
            po.append(
                polib.POEntry(
                    msgctxt=f"{namespace.name},{entry.key}",
                    msgid=entry.translation,
                )
            )
    po.save(str(po_path))
    return len(po)


def compile_locres(po_path, out_path):
    """Compile a PO into a .locres. Returns (written, dropped).

    Entries with neither msgstr nor msgid (untranslated, from the store) are
    dropped; writing them would show blank in game instead of English.
    """
    locres = LocresFile()
    locres.version = LocresVersion(LOCRES_VERSION)
    written = dropped = 0
    for entry in polib.pofile(str(po_path)):
        if entry.msgctxt is None or "," not in entry.msgctxt:
            continue
        # Not .strip(): a whitespace-only msgid is real game content.
        if not entry.msgstr and not entry.msgid:
            dropped += 1
            continue
        name, key = entry.msgctxt.split(",", 1)
        namespace = locres[name] or Namespace(name)
        locres.add(namespace)
        namespace.add(Entry(key, entry.msgstr or entry.msgid, entry.msgid, False))
        written += 1
    locres.write(str(out_path))
    return written, dropped


@dataclass
class Progress:
    translated: int = 0         # entries
    total: int = 0
    translated_words: int = 0   # English words, counted in msgid
    total_words: int = 0

    @property
    def percent(self):
        """Share of English words translated; words, so labels weigh less than paragraphs."""
        return self.translated_words / self.total_words * 100 if self.total_words else 0.0


def progress(po_path):
    """Progress for a PO file. Needs the working copy; the store has no msgids."""
    result = Progress()
    for entry in polib.pofile(str(po_path)):
        words = len(entry.msgid.split())
        result.total += 1
        result.total_words += words
        if entry.msgstr.strip():
            result.translated += 1
            result.translated_words += words
    return result


def load_store(store_path):
    if not store_path.exists():
        return {}
    return {
        e.msgctxt: e.msgstr
        for e in polib.pofile(str(store_path))
        if e.msgctxt is not None
    }


def dump_store(store):
    # No wrapping, so editing a word doesn't re-diff a whole paragraph.
    po = polib.POFile(wrapwidth=0)
    po.metadata = dict(STORE_METADATA)
    for msgctxt, msgstr in sorted(store.items()):
        po.append(polib.POEntry(msgctxt=msgctxt, msgid="", msgstr=msgstr))
    return str(po)


def save_store(store, store_path):
    text = dump_store(store)
    if store_path.exists() and store_path.read_text(encoding="utf-8") == text:
        return False
    store_path.write_text(text, encoding="utf-8")
    return True


def po_to_store(po_path, store_path):
    """Flush the working copy's translations into the source-controlled store."""
    if not po_path.exists():
        return False
    po = polib.pofile(str(po_path))
    store = {e.msgctxt: e.msgstr for e in po if e.msgctxt is not None}
    return save_store(store, store_path)


def store_to_po(po_path, store_path):
    """Apply the store onto the working copy.

    Returns (changed, orphans): orphans are store keys the game no longer has.
    """
    if not po_path.exists():
        return False, 0
    po = polib.pofile(str(po_path))
    store = load_store(store_path)
    unmatched = set(store)
    changed = False
    for entry in po:
        translation = store.get(entry.msgctxt, "")
        unmatched.discard(entry.msgctxt)
        if entry.msgstr != translation:
            entry.msgstr = translation
            changed = True
    if changed:
        po.save(str(po_path))
    return changed, len(unmatched)
