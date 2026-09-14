#!/usr/bin/env python3
"""Add a language to Astroneer's in-game language dropdown.

The dropdown is not built from the locres files on disk. It is built from a
single cooked data asset, Astro/Content/Globals/LocalizationCultureOptions,
which holds one property:

    TMap<FString, FString> DisplayLanguageToCultureMapping

mapping the label shown in the menu to the culture code the game switches to
("ENGLISH" -> "en-US", "Deutsch" -> "de", ...). Danish is simply not in that
map, which is why -culture=da works but the language never appears in the list.

This rewrites the pair of cooked files with an extra entry appended to the map:

    LocalizationCultureOptions.uexp    the serialized property data (the map)
    LocalizationCultureOptions.uasset  the package header (sizes/offsets)

Only three numbers change besides the inserted bytes: the MapProperty's tag
size, the export's SerialSize, and the package's BulkDataStartOffset.

Both files must be shipped together in the mod pak; the game reads the header
from the .uasset and the data from the .uexp.
"""

import argparse
import struct
import sys

PACKAGE_FILE_TAG = 0x9E2A83C1


class Reader:
    def __init__(self, data, name="file"):
        self.data = data
        self.name = name
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError(f"unexpected end of {self.name}")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]

    def fstring(self):
        """UE FString: int32 length; positive = ASCII, negative = UTF-16LE.

        The length counts the trailing NUL in both cases.
        """
        length = self.i32()
        if length == 0:
            return ""
        if length > 0:
            raw = self.take(length)
            return raw[:-1].decode("utf-8", errors="strict")
        raw = self.take(-length * 2)
        return raw[:-2].decode("utf-16-le")

    def fname(self):
        """FName reference in a cooked package: name-table index + number."""
        index = self.u32()
        number = self.u32()
        return index, number


def write_fstring(value):
    if all(ord(c) < 128 for c in value):
        raw = value.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = value.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def read_name_table(data):
    """Parse just enough of the package summary to read the name table.

    Returns (names, bulk_data_offset_pos, export_offset, export_count).
    """
    r = Reader(data, "uasset")
    if r.u32() != PACKAGE_FILE_TAG:
        raise ValueError("not a .uasset (bad package tag)")
    legacy_version = r.i32()
    if legacy_version != -7:
        raise ValueError(f"unsupported legacy package version {legacy_version}")
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
        raise ValueError("compressed chunks are not supported")
    r.u32()                                   # PackageSource
    for _ in range(r.i32()):                  # AdditionalPackagesToCook
        r.fstring()
    r.i32()                                   # AssetRegistryDataOffset
    bulk_pos = r.pos                          # BulkDataStartOffset (int64)

    names = []
    n = Reader(data, "uasset name table")
    n.pos = name_offset
    for _ in range(name_count):
        names.append(n.fstring())
        n.take(4)                             # precalculated hashes
    return names, bulk_pos, export_offset, export_count


def export_serial_size_pos(export_offset):
    """Byte offset of the first export's SerialSize (int64) in the header."""
    # ClassIndex, SuperIndex, TemplateIndex, OuterIndex (4x int32),
    # ObjectName (FName, 8 bytes), ObjectFlags (uint32), then SerialSize.
    return export_offset + 4 * 4 + 8 + 4


def parse_map(uexp, names, prop_name):
    """Locate the TMap<FString,FString> property and return its entries."""
    r = Reader(uexp, "uexp")
    tag_start = r.pos
    name_index, _ = r.fname()
    if names[name_index] != prop_name:
        raise ValueError(f"first property is '{names[name_index]}', expected '{prop_name}'")
    type_index, _ = r.fname()
    if names[type_index] != "MapProperty":
        raise ValueError(f"'{prop_name}' is a {names[type_index]}, expected MapProperty")
    size_pos = r.pos
    size = r.i32()
    r.i32()                                   # ArrayIndex
    key_type, _ = r.fname()
    value_type, _ = r.fname()
    for label, index in (("key", key_type), ("value", value_type)):
        if names[index] != "StrProperty":
            raise ValueError(f"map {label} type is {names[index]}, expected StrProperty")
    if r.u8() != 0:
        raise ValueError("property has a guid, which is not supported")

    value_start = r.pos
    if r.i32() != 0:
        raise ValueError("map has keys-to-remove, which is not supported")
    entries = [(r.fstring(), r.fstring()) for _ in range(r.i32())]
    value_end = r.pos
    if value_end - value_start != size:
        raise ValueError(f"map ran to {value_end - value_start} bytes, tag says {size}")
    del tag_start
    return entries, size_pos, value_start, value_end


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uasset", required=True, help="source LocalizationCultureOptions.uasset")
    ap.add_argument("--uexp", required=True, help="source LocalizationCultureOptions.uexp")
    ap.add_argument("--out-uasset", required=True, help="patched .uasset to write")
    ap.add_argument("--out-uexp", required=True, help="patched .uexp to write")
    ap.add_argument("--culture", "-c", required=True, help="culture code to add, e.g. da")
    ap.add_argument("--display", "-d", required=True,
                    help="label shown in the menu, e.g. Dansk")
    ap.add_argument("--property", default="DisplayLanguageToCultureMapping",
                    help="map property to patch (default: %(default)s)")
    ap.add_argument("--list", action="store_true",
                    help="print the current map and exit without writing")
    args = ap.parse_args()

    with open(args.uasset, "rb") as fh:
        uasset = bytearray(fh.read())
    with open(args.uexp, "rb") as fh:
        uexp = bytearray(fh.read())

    try:
        names, bulk_pos, export_offset, export_count = read_name_table(bytes(uasset))
        if export_count != 1:
            raise ValueError(f"expected 1 export, found {export_count}")
        entries, size_pos, value_start, value_end = parse_map(bytes(uexp), names, args.property)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    if args.list:
        for display, culture in entries:
            print(f"  {display}  ->  {culture}")
        return

    existing = {c.lower(): d for d, c in entries}
    if args.culture.lower() in existing:
        print(f"'{args.culture}' already in the language list as "
              f"'{existing[args.culture.lower()]}'; copying through unchanged")
        patched_uasset, patched_uexp = bytes(uasset), bytes(uexp)
    else:
        entries.append((args.display, args.culture))
        new_value = (
            struct.pack("<i", 0)                          # NumKeysToRemove
            + struct.pack("<i", len(entries))             # entry count
            + b"".join(write_fstring(d) + write_fstring(c) for d, c in entries)
        )
        delta = len(new_value) - (value_end - value_start)

        patched_uexp = bytes(uexp[:value_start]) + new_value + bytes(uexp[value_end:])
        patched_uexp = bytearray(patched_uexp)
        struct.pack_into("<i", patched_uexp, size_pos, len(new_value))

        # The header carries two byte counts that follow the .uexp's size.
        size_field = export_serial_size_pos(export_offset)
        serial_size = struct.unpack_from("<q", uasset, size_field)[0]
        bulk_start = struct.unpack_from("<q", uasset, bulk_pos)[0]
        struct.pack_into("<q", uasset, size_field, serial_size + delta)
        struct.pack_into("<q", uasset, bulk_pos, bulk_start + delta)
        patched_uasset, patched_uexp = bytes(uasset), bytes(patched_uexp)

        print(f"added '{args.display}' -> '{args.culture}' "
              f"({len(entries)} languages, .uexp +{delta} bytes)")

    with open(args.out_uasset, "wb") as fh:
        fh.write(patched_uasset)
    with open(args.out_uexp, "wb") as fh:
        fh.write(patched_uexp)


if __name__ == "__main__":
    main()
