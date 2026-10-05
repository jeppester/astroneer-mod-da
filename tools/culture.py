"""Add a language to Astroneer's in-game language dropdown.

The dropdown is built from the cooked asset
Astro/Content/Globals/LocalizationCultureOptions, not from locres files. Its one
property is a TMap<FString, FString> DisplayLanguageToCultureMapping from menu
label to culture code ("Deutsch" -> "de"). Danish is missing from it, so
-culture=da works but the language never shows up in the list.

add_language appends an entry in the .uexp (the map) and fixes up the .uasset
header: the MapProperty tag size, the export's SerialSize and the package's
BulkDataStartOffset. Both files must ship in the pak.
"""

import struct

from .console import Failure

PACKAGE_FILE_TAG = 0x9E2A83C1
MAP_PROPERTY = "DisplayLanguageToCultureMapping"


class _Reader:
    def __init__(self, data, name="file"):
        self.data = data
        self.name = name
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise Failure(f"unexpected end of {self.name}")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def fstring(self):
        """UE FString: int32 length incl. NUL; positive = ASCII, negative = UTF-16LE."""
        length = self.i32()
        if length == 0:
            return ""
        if length > 0:
            return self.take(length)[:-1].decode("utf-8")
        return self.take(-length * 2)[:-2].decode("utf-16-le")

    def fname(self):
        """Name-table index + number."""
        return self.u32(), self.u32()


def _write_fstring(value):
    if value.isascii():
        raw = value.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = value.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def _read_name_table(data):
    """Returns (names, bulk_data_offset_pos, export_offset, export_count)."""
    r = _Reader(data, "uasset")
    if r.u32() != PACKAGE_FILE_TAG:
        raise Failure("not a .uasset (bad package tag)")
    legacy_version = r.i32()
    if legacy_version != -7:
        raise Failure(f"unsupported legacy package version {legacy_version}")
    r.i32()                                   # LegacyUE3Version
    r.i32()                                   # FileVersionUE4
    r.i32()                                   # FileVersionLicenseeUE4
    for _ in range(r.i32()):                  # CustomVersions
        r.take(20)
    r.i32()                                   # TotalHeaderSize
    r.fstring()                               # FolderName
    r.u32()                                   # PackageFlags
    name_count = r.i32()
    name_offset = r.i32()
    r.i32(); r.i32()                          # GatherableTextData count/offset
    export_count = r.i32()
    export_offset = r.i32()
    r.i32(); r.i32()                          # Import count/offset
    r.i32()                                   # DependsOffset
    r.i32(); r.i32()                          # SoftPackageReferences count/offset
    r.i32()                                   # SearchableNamesOffset
    r.i32()                                   # ThumbnailTableOffset
    r.take(16)                                # Guid
    for _ in range(r.i32()):                  # Generations
        r.i32(); r.i32()
    for _ in range(2):                        # Saved/CompatibleWith EngineVersion
        r.take(2 * 3)
        r.u32()
        r.fstring()
    r.u32()                                   # CompressionFlags
    if r.i32() != 0:                          # CompressedChunks
        raise Failure("compressed chunks are not supported")
    r.u32()                                   # PackageSource
    for _ in range(r.i32()):                  # AdditionalPackagesToCook
        r.fstring()
    r.i32()                                   # AssetRegistryDataOffset
    bulk_pos = r.pos                          # BulkDataStartOffset (int64)

    names = []
    table = _Reader(data, "uasset name table")
    table.pos = name_offset
    for _ in range(name_count):
        names.append(table.fstring())
        table.take(4)                         # precalculated hashes
    return names, bulk_pos, export_offset, export_count


def _export_serial_size_pos(export_offset):
    """Offset of the first export's SerialSize (int64)."""
    # Skips ClassIndex, SuperIndex, TemplateIndex, OuterIndex, ObjectName, ObjectFlags.
    return export_offset + 4 * 4 + 8 + 4


def _parse_map(uexp, names, prop_name):
    """Returns (entries, size_pos, value_start, value_end) of the map property."""
    r = _Reader(uexp, "uexp")
    name_index, _ = r.fname()
    if names[name_index] != prop_name:
        raise Failure(f"first property is '{names[name_index]}', expected '{prop_name}'")
    type_index, _ = r.fname()
    if names[type_index] != "MapProperty":
        raise Failure(f"'{prop_name}' is a {names[type_index]}, expected MapProperty")
    size_pos = r.pos
    size = r.i32()
    r.i32()                                   # ArrayIndex
    key_type, _ = r.fname()
    value_type, _ = r.fname()
    for label, index in (("key", key_type), ("value", value_type)):
        if names[index] != "StrProperty":
            raise Failure(f"map {label} type is {names[index]}, expected StrProperty")
    if r.u8() != 0:
        raise Failure("property has a guid, which is not supported")

    value_start = r.pos
    if r.i32() != 0:
        raise Failure("map has keys-to-remove, which is not supported")
    entries = [(r.fstring(), r.fstring()) for _ in range(r.i32())]
    value_end = r.pos
    if value_end - value_start != size:
        raise Failure(f"map ran to {value_end - value_start} bytes, tag says {size}")
    return entries, size_pos, value_start, value_end


def read_languages(uasset, uexp, prop_name=MAP_PROPERTY):
    """The (display name, culture code) pairs in the dropdown."""
    names, _, _export_offset, export_count = _read_name_table(bytes(uasset))
    if export_count != 1:
        raise Failure(f"expected 1 export, found {export_count}")
    entries, _, _, _ = _parse_map(bytes(uexp), names, prop_name)
    return entries


def add_language(uasset, uexp, culture, display, prop_name=MAP_PROPERTY):
    """Return (uasset, uexp, entries, bytes added); unchanged if already listed."""
    uasset = bytearray(uasset)
    uexp = bytes(uexp)

    names, bulk_pos, export_offset, export_count = _read_name_table(bytes(uasset))
    if export_count != 1:
        raise Failure(f"expected 1 export, found {export_count}")
    entries, size_pos, value_start, value_end = _parse_map(uexp, names, prop_name)

    existing = {code.lower(): label for label, code in entries}
    if culture.lower() in existing:
        return bytes(uasset), uexp, entries, 0

    entries = [*entries, (display, culture)]
    new_value = (
        struct.pack("<i", 0)                          # NumKeysToRemove
        + struct.pack("<i", len(entries))             # entry count
        + b"".join(_write_fstring(d) + _write_fstring(c) for d, c in entries)
    )
    delta = len(new_value) - (value_end - value_start)

    patched_uexp = bytearray(uexp[:value_start] + new_value + uexp[value_end:])
    struct.pack_into("<i", patched_uexp, size_pos, len(new_value))

    size_field = _export_serial_size_pos(export_offset)
    serial_size = struct.unpack_from("<q", uasset, size_field)[0]
    bulk_start = struct.unpack_from("<q", uasset, bulk_pos)[0]
    struct.pack_into("<q", uasset, size_field, serial_size + delta)
    struct.pack_into("<q", uasset, bulk_pos, bulk_start + delta)

    return bytes(uasset), bytes(patched_uexp), entries, delta
