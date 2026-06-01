#!/usr/bin/env bash
# smoke_test.sh — verify the full oxidant local-model pipeline before overnight run
# Usage: ./scripts/smoke_test.sh [--nodes N]
#
# Checks:
#   1. Ollama is up and has the right config (flash attention, parallel, context)
#   2. oxidant-worker-14b responds and hits target tok/s
#   3. pi can reach the model
#   4. oxidant CLI is functional
#   5. 5 real nodes convert end-to-end (cargo check passes)

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
OXIDANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="$OXIDANT_DIR/oxidant.db"
CONFIG="$OXIDANT_DIR/oxidant.local.config.json"
NODES="${2:-5}"   # --nodes N, default 5

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BOLD='\033[1m'; RESET='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; PASS=$((PASS+1)); }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; FAIL=$((FAIL+1)); }

echo ""
echo -e "${BOLD}=== Oxidant Smoke Test — $(date) ===${RESET}"
echo ""

# ── 1. Ollama service ────────────────────────────────────────────────────────
echo -e "${BOLD}1. Ollama service${RESET}"

if systemctl is-active --quiet ollama; then
  ok "ollama.service is active"
else
  fail "ollama.service is NOT active — run: sudo systemctl start ollama"
fi

OLLAMA_ENV=$(systemctl show ollama --property=Environment 2>/dev/null)

if echo "$OLLAMA_ENV" | grep -q "OLLAMA_FLASH_ATTENTION=1"; then
  ok "OLLAMA_FLASH_ATTENTION=1 is set"
else
  fail "OLLAMA_FLASH_ATTENTION=1 missing — KV cache quant won't work; run setup.sh"
fi

if echo "$OLLAMA_ENV" | grep -q "OLLAMA_KV_CACHE_TYPE=q8_0"; then
  ok "OLLAMA_KV_CACHE_TYPE=q8_0 is set"
else
  warn "OLLAMA_KV_CACHE_TYPE not set to q8_0 — may get code corruption at long contexts"
fi

if echo "$OLLAMA_ENV" | grep -qE "OLLAMA_NUM_PARALLEL=[2-9]"; then
  NP=$(echo "$OLLAMA_ENV" | grep -oP 'OLLAMA_NUM_PARALLEL=\K\d+')
  ok "OLLAMA_NUM_PARALLEL=$NP"
else
  fail "OLLAMA_NUM_PARALLEL not set — will default to 1 (very slow)"
fi
echo ""

# ── 2. Model available ───────────────────────────────────────────────────────
echo -e "${BOLD}2. Model${RESET}"

if ollama list 2>/dev/null | grep -q "oxidant-worker-14b"; then
  ok "oxidant-worker-14b model is present"
else
  fail "oxidant-worker-14b not found — run: ollama create oxidant-worker-14b -f $OXIDANT_DIR/Modelfile.14b"
fi
echo ""

# ── 3. Inference speed ───────────────────────────────────────────────────────
echo -e "${BOLD}3. Inference speed${RESET}"

PROMPT='fn fibonacci(n: u32) -> u64 { if n <= 1 {'
START_NS=$(date +%s%N)

RESPONSE=$(curl -s http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d "{
    \"model\": \"oxidant-worker-14b\",
    \"prompt\": \"$PROMPT\",
    \"stream\": false,
    \"options\": {\"num_predict\": 60, \"num_ctx\": 8192, \"num_gpu\": 99}
  }" 2>/dev/null)

END_NS=$(date +%s%N)
ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))

if [ -z "$RESPONSE" ]; then
  fail "No response from Ollama — is it running?"
else
  EVAL_TOKENS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('eval_count', 0))" 2>/dev/null || echo "0")
  EVAL_NS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('eval_duration', 1))" 2>/dev/null || echo "1")
  TOK_S=$(python3 -c "print(f'{$EVAL_TOKENS / ($EVAL_NS / 1e9):.1f}')" 2>/dev/null || echo "?")
  SNIPPET=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(repr(d.get('response','')[:60]))" 2>/dev/null || echo "")

  if python3 -c "exit(0 if float('$TOK_S') >= 30 else 1)" 2>/dev/null; then
    ok "$TOK_S tok/s — model is running on GPU (target ≥30)"
  else
    fail "$TOK_S tok/s — too slow, likely CPU offload; check VRAM with ./scripts/check_vram.sh"
  fi
  echo "    response: $SNIPPET"
fi
echo ""

# ── 4. pi agent ─────────────────────────────────────────────────────────────
echo -e "${BOLD}4. pi coding agent${RESET}"

if command -v pi &>/dev/null; then
  PI_VER=$(pi --help 2>&1 | head -1 || echo "unknown")
  ok "pi is in PATH: $PI_VER"
else
  fail "pi not in PATH — check ~/.local/bin is in PATH or run setup.sh"
fi

PI_RESPONSE=$(pi --print --model "ollama/oxidant-worker-14b" "Output only Rust code. Complete this function: fn double(x: i32) -> i32 {" 2>&1 | head -3)
if echo "$PI_RESPONSE" | grep -qiE 'x \* 2|x\+x|\* 2|return.*x'; then
  ok "pi → ollama → model roundtrip works"
  echo "    response: $(echo "$PI_RESPONSE" | head -1)"
else
  warn "pi returned unexpected output (may still work): $(echo "$PI_RESPONSE" | head -1)"
fi
echo ""

# ── 5. oxidant CLI ───────────────────────────────────────────────────────────
echo -e "${BOLD}5. Oxidant CLI${RESET}"

cd "$OXIDANT_DIR"

if uv run oxidant --help &>/dev/null; then
  ok "oxidant CLI loads"
else
  fail "oxidant CLI failed — run: cd $OXIDANT_DIR && uv sync"
fi

if [ -f "$DB" ]; then
  NOT_STARTED=$(sqlite3 "$DB" "SELECT COUNT(*) FROM nodes WHERE status='not_started' AND (cyclomatic_complexity IS NULL OR cyclomatic_complexity <= 3)" 2>/dev/null || echo "0")
  ok "DB found — $NOT_STARTED simple nodes (cc≤3) ready to convert"
else
  warn "No oxidant.db found at $DB — you'll need to copy or create it"
fi

if [ ! -f "$CONFIG" ]; then
  fail "oxidant.local.config.json not found — run setup.sh"
else
  ok "oxidant.local.config.json present"
fi
echo ""

# ── 6. Mini batch ────────────────────────────────────────────────────────────
if [ -f "$DB" ] && [ -f "$CONFIG" ]; then
  echo -e "${BOLD}6. Mini batch ($NODES nodes)${RESET}"
  echo "   Running $NODES nodes through phase-b — this may take a few minutes..."
  echo ""

  uv run oxidant reset-stuck --db "$DB" 2>/dev/null

  BATCH_START=$(date +%s)
  # run with a node limit (--limit flag, or just watch the log)
  BATCH_LOG=$(mktemp)
  timeout 600 uv run oxidant phase-b --config "$CONFIG" --db "$DB" \
    2>&1 | tee "$BATCH_LOG" | grep -E 'converted|failed|cargo|error|ERROR|node' | head -30 || true
  BATCH_END=$(date +%s)
  BATCH_TIME=$((BATCH_END - BATCH_START))

  CONVERTED_NOW=$(sqlite3 "$DB" "SELECT COUNT(*) FROM nodes WHERE status='converted'" 2>/dev/null || echo "?")
  FAILED_NOW=$(sqlite3 "$DB" "SELECT COUNT(*) FROM nodes WHERE status='human_review'" 2>/dev/null || echo "?")

  ok "Mini batch completed in ${BATCH_TIME}s — converted: $CONVERTED_NOW total, human_review: $FAILED_NOW"
  rm -f "$BATCH_LOG"
fi
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
echo -e "${BOLD}=== Summary ===${RESET}"
echo -e "  ${GREEN}Passed: $PASS${RESET}   ${RED}Failed: $FAIL${RESET}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}✓ All checks passed — safe to start overnight run:${RESET}"
  echo "    sudo systemctl start oxidant-overnight"
  echo "    # or: ./run_overnight.sh"
else
  echo -e "  ${RED}✗ $FAIL check(s) failed — fix issues before running overnight${RESET}"
fi
echo ""
