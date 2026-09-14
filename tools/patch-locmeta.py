#!/usr/bin/env python3
"""Add a culture to an Unreal Engine .locmeta file.

The stock Astro/Content/Localization/Game/Game.locmeta lists the 14 cultures the
game shipped with. Danish is not among them, so a da/Game.locres dropped in via
a mod pak has no entry in the manifest. This rewrites the manifest with the new
culture inserted, leaving the native culture and native locres path untouched.

Format (ELocMetaVersion 1 = AddedCompiledCultures):
    FGuid  magic (16 bytes)
    uint8  version
    FString NativeCulture
    FString NativeLocResFilename
    TArray<FString> CompiledCultures

FString here is: int32 length (byte count, including the trailing NUL) followed
by that many ASCII bytes. (UE writes negative lengths for UTF-16 strings; culture
codes are always ASCII, so we only handle the positive case and bail otherwise.)
"""

import argparse
import struct
import sys

LOCMETA_MAGIC = bytes(
    [0x4F, 0xEE, 0x4C, 0xA1, 0x68, 0x48, 0x55, 0x83,
     0x6C, 0x4C, 0x46, 0xBD, 0x70, 0xDA, 0x50, 0x7C]
)


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("unexpected end of locmeta")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def string(self):
        length = self.i32()
        if length < 0:
            raise ValueError("UTF-16 strings in locmeta are not supported")
        if length == 0:
            return ""
        raw = self.take(length)
        if raw[-1] != 0:
            raise ValueError("string not NUL-terminated")
        return raw[:-1].decode("ascii")


def write_string(value):
    raw = value.encode("ascii") + b"\0"
    return struct.pack("<i", len(raw)) + raw


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "-i", required=True, help="source Game.locmeta")
    ap.add_argument("--out", "-o", required=True, help="patched Game.locmeta to write")
    ap.add_argument("--culture", "-c", required=True, help="culture code to add, e.g. da")
    args = ap.parse_args()

    with open(args.input, "rb") as fh:
        data = fh.read()

    r = Reader(data)
    magic = r.take(16)
    if magic != LOCMETA_MAGIC:
        sys.exit(f"error: {args.input} is not a .locmeta (bad magic)")

    version = r.u8()
    if version < 1:
        sys.exit(f"error: locmeta version {version} has no compiled-culture list to patch")

    native_culture = r.string()
    native_locres = r.string()

    count = r.i32()
    cultures = [r.string() for _ in range(count)]

    if r.pos != len(data):
        sys.exit(f"error: {len(data) - r.pos} trailing bytes; refusing to write a lossy file")

    if args.culture in cultures:
        print(f"'{args.culture}' already present in {args.input}; copying through unchanged")
        patched = data
    else:
        cultures.append(args.culture)
        cultures.sort()
        patched = (
            LOCMETA_MAGIC
            + bytes([version])
            + write_string(native_culture)
            + write_string(native_locres)
            + struct.pack("<i", len(cultures))
            + b"".join(write_string(c) for c in cultures)
        )
        print(f"added '{args.culture}' -> {len(cultures)} cultures: {', '.join(cultures)}")

    with open(args.out, "wb") as fh:
        fh.write(patched)


if __name__ == "__main__":
    main()
