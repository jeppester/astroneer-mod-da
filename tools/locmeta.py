"""Add a culture to an Unreal Engine .locmeta file.

The stock Game.locmeta doesn't list Danish, so a da/Game.locres from a mod pak
has no manifest entry. add_culture inserts it and leaves the rest untouched.

Format (ELocMetaVersion 1 = AddedCompiledCultures):
    FGuid  magic (16 bytes)
    uint8  version
    FString NativeCulture
    FString NativeLocResFilename
    TArray<FString> CompiledCultures

FString: int32 byte length (including trailing NUL) + ASCII bytes. UE uses a
negative length for UTF-16; culture codes are ASCII, so that is rejected.
"""

import struct

from .console import Failure

MAGIC = bytes(
    [0x4F, 0xEE, 0x4C, 0xA1, 0x68, 0x48, 0x55, 0x83,
     0x6C, 0x4C, 0x46, 0xBD, 0x70, 0xDA, 0x50, 0x7C]
)


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise Failure("unexpected end of locmeta")
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
            raise Failure("UTF-16 strings in locmeta are not supported")
        if length == 0:
            return ""
        raw = self.take(length)
        if raw[-1] != 0:
            raise Failure("string not NUL-terminated")
        return raw[:-1].decode("ascii")


def _write_string(value):
    raw = value.encode("ascii") + b"\0"
    return struct.pack("<i", len(raw)) + raw


def read_cultures(data):
    """Return (version, native culture, native locres path, compiled cultures)."""
    reader = _Reader(data)
    if reader.take(16) != MAGIC:
        raise Failure("not a .locmeta (bad magic)")
    version = reader.u8()
    if version < 1:
        raise Failure(f"locmeta version {version} has no compiled-culture list")
    native_culture = reader.string()
    native_locres = reader.string()
    cultures = [reader.string() for _ in range(reader.i32())]
    if reader.pos != len(data):
        raise Failure(
            f"{len(data) - reader.pos} trailing bytes in locmeta; "
            "refusing to write a lossy file"
        )
    return version, native_culture, native_locres, cultures


def add_culture(data, culture):
    """Return (patched locmeta bytes, culture list). No-op if already listed."""
    version, native_culture, native_locres, cultures = read_cultures(data)
    if culture in cultures:
        return bytes(data), cultures

    cultures = sorted([*cultures, culture])
    patched = (
        MAGIC
        + bytes([version])
        + _write_string(native_culture)
        + _write_string(native_locres)
        + struct.pack("<i", len(cultures))
        + b"".join(_write_string(c) for c in cultures)
    )
    return patched, cultures
