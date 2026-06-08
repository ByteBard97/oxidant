#!/usr/bin/env bash
# Sync translated flightpath-rs source into data_acq_flightpath.
# Only copies src/*.rs and Cargo.toml — nothing else.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/corpora/flightpath-rs"
DEST="/Users/ceres/Desktop/GitHub/data_acq_flightpath/flightpath-rs"
DB="$SCRIPT_DIR/flightpath_manifest.db"

echo "Syncing $SRC → $DEST"

# Only sync source files and Cargo.toml — never target/, clones, lock files, or anything else
rsync -a --delete "$SRC/src/" "$DEST/src/"
cp "$SRC/Cargo.toml" "$DEST/Cargo.toml"

echo ""
echo "Checking Rust build..."
cd "$DEST"
cargo build 2>&1 | tail -2

python3 - <<'PYEOF'
import re
from pathlib import Path

files = ['src/units.rs','src/gis.rs','src/transect.rs','src/field.rs','src/flight_solver.rs']
print()
print('── Translation progress ──────────────────────────────')
grand_total = grand_done = 0
for f in files:
    p = Path(f)
    if not p.exists():
        continue
    text = p.read_text()
    total = len(re.findall(r'pub fn|pub const', text))
    stubs = text.count('todo!')
    done  = total - stubs
    grand_total += total; grand_done += done
    print(f'  {p.stem:<20}  {done}/{total} done')
print(f'\n  Total: {grand_done}/{grand_total} translated ({grand_total - grand_done} stubs remaining)')
PYEOF

if command -v sqlite3 &>/dev/null && [ -f "$DB" ]; then
    echo ""
    echo "── Manifest DB status ────────────────────────────────"
    sqlite3 "$DB" "SELECT '  ' || status || ': ' || COUNT(*) FROM nodes GROUP BY status;"
fi
