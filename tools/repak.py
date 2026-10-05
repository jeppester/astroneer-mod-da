"""Read and write Unreal .pak files through the bundled repak binary.

Use qualified (`repak.get(...)`, `repak.pack(...)`). The binary is checked on
first use, not at import.
"""

import subprocess
from pathlib import Path

from .console import Failure

BINARY = Path(__file__).resolve().parent / "repak" / "repak"

# Used when the base pak's format can't be read from `repak info`.
FALLBACK_VERSION = "V11"
FALLBACK_PATH_HASH_SEED = 0x1C2BCA8D


def _run(*args, binary_output=False):
    if not BINARY.is_file():
        raise Failure(f"{BINARY} not found")
    result = subprocess.run(
        [str(BINARY), *[str(a) for a in args]],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise Failure(f"repak {args[0]} failed: {detail or 'no error output'}")
    return result.stdout if binary_output else result.stdout.decode("utf-8", "replace")


def _list_files(pak):
    return [line for line in _run("list", pak).splitlines() if line.strip()]


def format_of(pak):
    """(version, path_hash_seed, matched); a patch pak must match its base pak's format."""
    try:
        info = _run("info", pak)
    except Failure:
        return FALLBACK_VERSION, FALLBACK_PATH_HASH_SEED, False
    version = seed = None
    for line in info.splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
        elif line.startswith("path hash seed:"):
            raw = line.split(":", 1)[1].strip()
            if raw.startswith("Some(") and raw.endswith(")"):
                seed = int(raw[5:-1], 16)
    if version and seed is not None:
        return version, seed, True
    return FALLBACK_VERSION, FALLBACK_PATH_HASH_SEED, False


def get(pak, path):
    return _run("get", pak, path, binary_output=True)


def pack(stage_dir, out, version, path_hash_seed, expected=()):
    """Pack a staged tree and verify the result contains `expected`."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    _run(
        "pack",
        "--version", version,
        "--path-hash-seed", path_hash_seed,
        stage_dir, out,
    )
    listing = _list_files(out)
    for wanted in expected:
        if wanted not in listing:
            raise Failure(f"packed pak {out} is missing {wanted}")
    return listing
