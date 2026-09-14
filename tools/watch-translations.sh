#!/usr/bin/env bash
#
# Keep translation/da.json (source-controlled) and translation/Game_da.po
# (gitignored working copy) in sync while you translate. Run this in the
# background and leave it running alongside Poedit.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO_DIR/tools/sync-translations.py" watch
