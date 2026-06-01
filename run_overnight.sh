#!/usr/bin/env bash
set -euo pipefail

DB="oxidant.db"
CONFIG="oxidant.local.config.json"
LOG="overnight_$(date +%Y%m%d_%H%M%S).log"

echo "=== Oxidant overnight run starting at $(date) ===" | tee "$LOG"

export PATH="$HOME/.local/bin:$PATH"

uv run oxidant reset-stuck --db "$DB" 2>&1 | tee -a "$LOG"

while true; do
    echo "--- Starting batch at $(date) ---" | tee -a "$LOG"

    uv run oxidant phase-b         --config "$CONFIG"         --db "$DB"         2>&1 | tee -a "$LOG"

    EXIT_CODE=${PIPESTATUS[0]}

    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "=== Phase B completed cleanly at $(date) ===" | tee -a "$LOG"
        break
    else
        echo "=== Exited $EXIT_CODE at $(date) — resetting stuck and retrying in 30s ===" | tee -a "$LOG"
        uv run oxidant reset-stuck --db "$DB" 2>&1 | tee -a "$LOG"
        sleep 30
    fi
done
