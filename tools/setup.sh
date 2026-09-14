#!/usr/bin/env bash
#
# One-time (re-runnable) project setup.
#
# This mod's source never carries game files or the game's original English
# strings — those get pulled fresh from your local Astroneer install instead.
# This script does that:
#
#   1. Extracts source-locres/ and source-assets/ from the base game pak.
#      Both are gitignored; they're regenerated here, not distributed.
#   2. Generates translation/Game_da.po (also gitignored) from the extracted
#      English strings, then applies the translations already recorded in
#      translation/da.json (the source-controlled translation store).
#
# Run it again any time the game updates and you want fresh source strings.
# Run tools/watch-translations.sh afterwards to keep da.json in sync while
# you edit Game_da.po.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

GAME_DIR="${ASTRONEER_DIR:-$HOME/.local/share/Steam/steamapps/common/ASTRONEER}"
BASE_PAK="$GAME_DIR/Astro/Content/Paks/pakchunk0-WindowsNoEditor.pak"
REPAK="tools/repak/repak"
CULTURE_ASSET_PATH="Astro/Content/Globals/LocalizationCultureOptions"
PO_FILE="translation/Game_da.po"
STORE_FILE="translation/da.json"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

say "Checking prerequisites"
[[ -x "$REPAK" ]] || die "$REPAK not found or not executable"
[[ -f "$BASE_PAK" ]] || die "base game pak not found at $BASE_PAK (set ASTRONEER_DIR to point at your Astroneer install)"
command -v pylocres >/dev/null || die "pylocres not found — install with: pip install --user pylocres"
python3 -c 'import polib' 2>/dev/null || die "python3 module 'polib' not found — install with: pip install --user polib"
ok "found game install and required tools"

if [[ -f "$PO_FILE" ]]; then
    say "Flushing any pending edits in the existing $PO_FILE into $STORE_FILE"
    python3 tools/sync-translations.py to-store
fi

say "Extracting source strings from the base pak"
mkdir -p source-locres/en
"$REPAK" get "$BASE_PAK" "Astro/Content/Localization/Game/en/Game.locres" > source-locres/en/Game.locres
"$REPAK" get "$BASE_PAK" "Astro/Content/Localization/Game/Game.locmeta" > source-locres/Game.locmeta
ok "source-locres/en/Game.locres, source-locres/Game.locmeta"

say "Extracting the language dropdown asset"
mkdir -p "source-assets/$(dirname "$CULTURE_ASSET_PATH")"
for ext in uasset uexp; do
    "$REPAK" get "$BASE_PAK" "$CULTURE_ASSET_PATH.$ext" > "source-assets/$CULTURE_ASSET_PATH.$ext"
done
ok "source-assets/$CULTURE_ASSET_PATH.{uasset,uexp}"

say "Generating $PO_FILE"
TMP_PO="$(mktemp)"
pylocres to-po -p source-locres/en/Game.locres -o "$TMP_PO" >/dev/null
mv "$TMP_PO" "$PO_FILE"
python3 tools/sync-translations.py to-po
python3 - "$PO_FILE" "$STORE_FILE" <<'PY'
import json, sys
import polib
po_path, store_path = sys.argv[1], sys.argv[2]
total = len(polib.pofile(po_path))
try:
    translated = len(json.load(open(store_path)))
except FileNotFoundError:
    translated = 0
pct = (translated / total * 100) if total else 0.0
print(f"  {translated}/{total} entries translated ({pct:.1f}%)")
PY
ok "$PO_FILE"

echo
echo "  Edit $PO_FILE in Poedit (https://poedit.net/) or a text editor."
echo "  Run ./tools/watch-translations.sh in the background to keep"
echo "  $STORE_FILE (source-controlled) in sync as you edit."
