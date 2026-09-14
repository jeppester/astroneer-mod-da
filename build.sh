#!/usr/bin/env bash
#
# Build the Astroneer Danish translation mod.
#
#   ./build.sh                 compile translation/Game_da.po -> mod-output/AstroneerDanish_P.pak
#   ./build.sh --install       ...and copy the pak into the game's Paks directory
#   ./build.sh --culture nb    build for a different culture code
#   ./build.sh --display Norsk label to show in the in-game language dropdown
#   ./build.sh --clean         remove build/ and mod-output/ artifacts, then exit
#
# Steps: po -> locres, patch the culture list into Game.locmeta, add the language to
# the in-game dropdown asset, stage the pak tree, pack it with the same pak format as
# the base game pak, verify the result.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

CULTURE="da"
DISPLAY_NAME="Dansk"
PO_FILE="translation/Game_da.po"
LOCMETA_SRC="source-locres/Game.locmeta"
# The in-game language dropdown is built from this cooked data asset, not from the
# locres files on disk. Vendored copies are the fallback; the build prefers to
# re-extract them from the installed base pak so a game update can't leave us
# shadowing a stale version of the asset.
CULTURE_ASSET_PATH="Astro/Content/Globals/LocalizationCultureOptions"
CULTURE_ASSET_SRC_DIR="source-assets/$(dirname "$CULTURE_ASSET_PATH")"
BUILD_DIR="build"
STAGE_DIR="$BUILD_DIR/pak"
OUT_PAK="mod-output/AstroneerDanish_P.pak"
REPAK="tools/repak/repak"
GAME_DIR="${ASTRONEER_DIR:-$HOME/.local/share/Steam/steamapps/common/ASTRONEER}"
BASE_PAK="$GAME_DIR/Astro/Content/Paks/pakchunk0-WindowsNoEditor.pak"

# Fallbacks used only when the base game pak isn't available to read the real
# values off of. These are what pakchunk0-WindowsNoEditor.pak reports today.
FALLBACK_PAK_VERSION="V11"
FALLBACK_PATH_HASH_SEED="0x1C2BCA8D"

DO_INSTALL=0
DO_CLEAN=0

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)  DO_INSTALL=1; shift ;;
        --clean)    DO_CLEAN=1; shift ;;
        --culture)  CULTURE="${2:?--culture needs a value}"; shift 2 ;;
        --display)  DISPLAY_NAME="${2:?--display needs a value}"; shift 2 ;;
        --po)       PO_FILE="${2:?--po needs a value}"; shift 2 ;;
        -h|--help)  sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)          die "unknown option: $1 (try --help)" ;;
    esac
done

if [[ $DO_CLEAN -eq 1 ]]; then
    say "Cleaning build artifacts"
    rm -rf "$BUILD_DIR"
    rm -f "$OUT_PAK"
    ok "removed $BUILD_DIR/ and $OUT_PAK"
    exit 0
fi

# ---------------------------------------------------------------- preflight
say "Checking prerequisites"

command -v python3 >/dev/null || die "python3 not found"
command -v pylocres >/dev/null || die "pylocres not found — install with: pip install --user pylocres"
python3 -c 'import polib' 2>/dev/null || die "python3 module 'polib' not found — install with: pip install --user polib"
[[ -x "$REPAK" ]] || die "$REPAK not found or not executable"
[[ -f "$PO_FILE" ]] || die "translation file not found: $PO_FILE (run ./tools/setup.sh first)"
[[ -f "$LOCMETA_SRC" ]] || die "locmeta not found: $LOCMETA_SRC (run ./tools/setup.sh first)"
[[ -f "tools/patch-locmeta.py" ]] || die "tools/patch-locmeta.py not found"
[[ -f "tools/patch-culture-options.py" ]] || die "tools/patch-culture-options.py not found"

ok "pylocres $(pylocres --version 2>/dev/null | tr -d '\n' || echo '?'), repak present"

# Read the pak format off the base game pak so the mod pak matches it exactly.
# A patch pak whose version or path-hash seed disagrees with the base pak can
# fail to mount, so prefer the real values whenever the game is installed.
if [[ -f "$BASE_PAK" ]]; then
    base_info="$("$REPAK" info "$BASE_PAK" 2>/dev/null || true)"
    PAK_VERSION="$(awk '/^version:/ {print $2}' <<<"$base_info")"
    seed_hex="$(sed -n 's/^path hash seed: Some(\(.*\))/\1/p' <<<"$base_info")"
    if [[ -n "$PAK_VERSION" && -n "$seed_hex" ]]; then
        PATH_HASH_SEED="0x${seed_hex}"
        ok "matched base pak format: $PAK_VERSION, path hash seed 0x${seed_hex}"
    else
        PAK_VERSION="$FALLBACK_PAK_VERSION"
        PATH_HASH_SEED="$FALLBACK_PATH_HASH_SEED"
        warn "could not parse base pak info; using defaults $PAK_VERSION / $PATH_HASH_SEED"
    fi
else
    PAK_VERSION="$FALLBACK_PAK_VERSION"
    PATH_HASH_SEED="$FALLBACK_PATH_HASH_SEED"
    warn "base pak not found at $BASE_PAK"
    warn "using defaults $PAK_VERSION / $PATH_HASH_SEED (set ASTRONEER_DIR to point at the install)"
fi

# repak wants the seed as a plain integer, not hex.
PATH_HASH_SEED_DEC=$(( PATH_HASH_SEED ))

# ------------------------------------------------------------ translation stats
say "Inspecting $PO_FILE"
python3 - "$PO_FILE" <<'PY'
import sys, polib
po = polib.pofile(sys.argv[1])
total = len(po)
done = sum(1 for e in po if e.msgstr.strip())
pct = (done / total * 100) if total else 0.0
print(f"  {done}/{total} entries translated ({pct:.1f}%), {total - done} will fall back to English")
PY

# ------------------------------------------------------------------- build
say "Staging pak tree"
rm -rf "$BUILD_DIR"
LOC_DIR="$STAGE_DIR/Astro/Content/Localization/Game"
mkdir -p "$LOC_DIR/$CULTURE"

# 1. Compile the .po into a .locres. Entries with an empty msgstr are written
#    out with their English msgid, so untranslated strings show up in English.
pylocres from-po -p "$PO_FILE" -o "$LOC_DIR/$CULTURE/Game.locres" >/dev/null \
    || die "pylocres from-po failed"
ok "compiled $LOC_DIR/$CULTURE/Game.locres ($(du -h "$LOC_DIR/$CULTURE/Game.locres" | cut -f1))"

# 2. The stock Game.locmeta lists only the cultures the game shipped with, and
#    it lives at the localization-target root — not inside the culture folder.
#    Add our culture so the new locres is part of the manifest.
python3 tools/patch-locmeta.py \
    --input "$LOCMETA_SRC" \
    --out "$LOC_DIR/Game.locmeta" \
    --culture "$CULTURE" \
    | sed 's/^/  /'

# 3. Add the language to the in-game dropdown. Nothing enumerates the locres
#    folders at runtime — the list comes from the DisplayLanguageToCultureMapping
#    map inside the LocalizationCultureOptions data asset, so the mod ships an
#    overriding copy of it with our culture appended. Without this the language
#    only works via the -culture=<code> launch option.
#    The .uasset/.uexp pair is re-extracted from the base pak when the game is
#    installed, so the override is always based on the current shipping asset.
GLOBALS_DIR="$STAGE_DIR/$(dirname "$CULTURE_ASSET_PATH")"
mkdir -p "$GLOBALS_DIR"
culture_asset_src="$CULTURE_ASSET_SRC_DIR"
if [[ -f "$BASE_PAK" ]]; then
    extract_dir="$BUILD_DIR/extracted"
    mkdir -p "$extract_dir"
    extract_ok=1
    for ext in uasset uexp; do
        "$REPAK" get "$BASE_PAK" "$CULTURE_ASSET_PATH.$ext" \
            > "$extract_dir/$(basename "$CULTURE_ASSET_PATH").$ext" 2>/dev/null \
            || extract_ok=0
    done
    if [[ $extract_ok -eq 1 ]]; then
        culture_asset_src="$extract_dir"
        ok "extracted $(basename "$CULTURE_ASSET_PATH") from the installed base pak"
        for ext in uasset uexp; do
            vendored="$CULTURE_ASSET_SRC_DIR/$(basename "$CULTURE_ASSET_PATH").$ext"
            if [[ -f "$vendored" ]] && ! cmp -s "$vendored" "$extract_dir/$(basename "$CULTURE_ASSET_PATH").$ext"; then
                warn "installed $(basename "$CULTURE_ASSET_PATH").$ext differs from the vendored copy in $CULTURE_ASSET_SRC_DIR/"
                warn "a game update likely changed it — refresh the vendored copy when convenient"
            fi
        done
    else
        warn "could not extract $CULTURE_ASSET_PATH from the base pak; using vendored copy"
    fi
fi
for ext in uasset uexp; do
    [[ -f "$culture_asset_src/$(basename "$CULTURE_ASSET_PATH").$ext" ]] \
        || die "missing $culture_asset_src/$(basename "$CULTURE_ASSET_PATH").$ext (run ./tools/setup.sh first, or set ASTRONEER_DIR)"
done
asset_base="$(basename "$CULTURE_ASSET_PATH")"
python3 tools/patch-culture-options.py \
    --uasset     "$culture_asset_src/$asset_base.uasset" \
    --uexp       "$culture_asset_src/$asset_base.uexp" \
    --out-uasset "$GLOBALS_DIR/$asset_base.uasset" \
    --out-uexp   "$GLOBALS_DIR/$asset_base.uexp" \
    --culture    "$CULTURE" \
    --display    "$DISPLAY_NAME" \
    | sed 's/^/  /'

# 4. Pack. The default mount point (../../../) resolves relative to
#    Astro/Content/Paks/, so the staged tree lands at the right game paths.
say "Packing $OUT_PAK"
mkdir -p "$(dirname "$OUT_PAK")"
rm -f "$OUT_PAK"
"$REPAK" pack \
    --version "$PAK_VERSION" \
    --path-hash-seed "$PATH_HASH_SEED_DEC" \
    "$STAGE_DIR" "$OUT_PAK" >/dev/null \
    || die "repak pack failed"

# ------------------------------------------------------------------ verify
say "Verifying"
listing="$("$REPAK" list "$OUT_PAK")"
expected_locres="Astro/Content/Localization/Game/$CULTURE/Game.locres"
expected_locmeta="Astro/Content/Localization/Game/Game.locmeta"
grep -qxF "$expected_locres"  <<<"$listing" || die "packed pak is missing $expected_locres"
grep -qxF "$expected_locmeta" <<<"$listing" || die "packed pak is missing $expected_locmeta"
for ext in uasset uexp; do
    grep -qxF "$CULTURE_ASSET_PATH.$ext" <<<"$listing" \
        || die "packed pak is missing $CULTURE_ASSET_PATH.$ext"
done
sed 's/^/  /' <<<"$listing"
ok "$OUT_PAK ($(du -h "$OUT_PAK" | cut -f1))"

# ----------------------------------------------------------------- install
if [[ $DO_INSTALL -eq 1 ]]; then
    dest_dir="$GAME_DIR/Astro/Content/Paks"
    [[ -d "$dest_dir" ]] || die "game Paks directory not found: $dest_dir"
    say "Installing to $dest_dir"
    cp "$OUT_PAK" "$dest_dir/"
    ok "installed $(basename "$OUT_PAK")"
    echo
    echo "  Pick '$DISPLAY_NAME' in Options > Language, or force it with the"
    echo "  launch option:  -culture=$CULTURE"
else
    echo
    echo "  Not installed. To install:  ./build.sh --install"
    echo "  Or copy manually:           cp $OUT_PAK '$GAME_DIR/Astro/Content/Paks/'"
    echo "  Then pick '$DISPLAY_NAME' in Options > Language (or launch with -culture=$CULTURE)"
fi
