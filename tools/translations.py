"""The two PO files, and the locres the game actually reads.

translation/da.po is the source-controlled translation store: a msgctxt ->
msgstr map containing only text this project's translators wrote. Every entry
has an empty msgid, so the file carries none of the game's English strings and
is safe to distribute. The game looks strings up by msgctxt (its namespace +
string hash), so msgid is not needed to identify an entry.

It holds EVERY key the game has, including ones nobody has translated yet —
those simply have an empty msgstr. That keeps the full key set under version
control (so progress is measurable and a key disappearing from the game is
visible in a diff) at no risk of leaking English text, since both msgid and
msgstr are empty for an untranslated entry. Such an entry has nothing to
compile: compile_locres drops it rather than writing an empty string into the
locres, which would render blank in game instead of falling back to English.

PO was chosen over JSON/YAML because it treats every string the same way: the
value is always quoted and a newline is always an explicit "\\n", so a
multi-line translation still shows its line structure without any whitespace
ever landing at the end of a physical line, where an editor or hook that trims
line ends could eat it. "msgfmt --check" validates the result.

translation/Game_da.po is the generated working copy. It also carries the
original English msgid text, needed to translate in Poedit or any PO editor.
It's gitignored and rebuilt from the game's own files on every start.
"""

import polib
from pylocres import Entry, LocresFile, LocresVersion, Namespace

# The locres version the game ships and the one we write back. 3 = CityHash.
LOCRES_VERSION = 3

# Fixed on purpose: anything time-based here (POT-Creation-Date,
# PO-Revision-Date) would rewrite the store on every sync and churn history.
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

    An entry with an empty msgstr but a real msgid (the normal case in the
    working Game_da.po) is written out with its English msgid, so untranslated
    strings show up in English. An entry with NEITHER — what the store carries
    for a string nobody has translated yet — has nothing to write, and would
    otherwise become a real entry holding an empty string, showing up blank in
    game rather than falling back to English. Those are dropped, so building
    straight from translation/da.po is safe.
    """
    locres = LocresFile()
    locres.version = LocresVersion(LOCRES_VERSION)
    written = dropped = 0
    for entry in polib.pofile(str(po_path)):
        if entry.msgctxt is None or "," not in entry.msgctxt:
            continue
        # Exact emptiness, not .strip(): a msgid of "   " is real game content
        # (a deliberately blank-looking string) and must still be compiled.
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


def progress(po_path):
    """(translated, total) for a PO file."""
    po = polib.pofile(str(po_path))
    return sum(1 for e in po if e.msgstr.strip()), len(po)


def load_store(store_path):
    if not store_path.exists():
        return {}
    # Entries the store wrote all carry a msgctxt; the file header does not.
    return {
        e.msgctxt: e.msgstr
        for e in polib.pofile(str(store_path))
        if e.msgctxt is not None
    }


def dump_store(store):
    # wrapwidth=0 disables line wrapping, so one logical line stays one physical
    # line and editing a word doesn't reflow (and re-diff) a whole paragraph.
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
    # Every key, translated or not — an untranslated one is stored with an empty
    # msgstr so the key set itself stays under version control.
    store = {e.msgctxt: e.msgstr for e in po if e.msgctxt is not None}
    return save_store(store, store_path)


def store_to_po(po_path, store_path):
    """Apply the store's translations onto the working copy.

    Returns (changed, orphans): orphans are translations with no matching
    string in the working copy, i.e. keys the game no longer has.
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
