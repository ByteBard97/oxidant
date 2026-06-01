#!/usr/bin/env bash
# check_vram.sh — VRAM snapshot before starting an oxidant overnight run
# Usage: ./scripts/check_vram.sh [--model 14b|30b]

set -euo pipefail

MODEL="${1:-14b}"

# Thresholds (MiB)
MODEL_14B_WEIGHTS=9200    # Q4_K_M weights
MODEL_14B_KV_4P=1650      # q8_0 KV, 4 parallel × 8192 ctx
MODEL_14B_OVERHEAD=800    # CUDA graphs, activations, Ollama overhead
MODEL_14B_TOTAL=$((MODEL_14B_WEIGHTS + MODEL_14B_KV_4P + MODEL_14B_OVERHEAD))   # ~11650 MiB

MODEL_30B_WEIGHTS=14130   # UD-Q3_K_XL
MODEL_30B_KV_2P=830       # q8_0 KV, 2 parallel × 8192 ctx
MODEL_30B_OVERHEAD=800
MODEL_30B_TOTAL=$((MODEL_30B_WEIGHTS + MODEL_30B_KV_2P + MODEL_30B_OVERHEAD))   # ~15760 MiB

VRAM_TOTAL_MIB=16303      # RTX 5080

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BOLD='\033[1m'; RESET='\033[0m'

echo ""
echo -e "${BOLD}=== VRAM Check — $(date) ===${RESET}"
echo ""

# --- Raw GPU numbers ---
read -r total_mib used_mib free_mib <<< $(
  nvidia-smi --query-gpu=memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits 2>/dev/null | tr ',' ' '
)

pct_used=$(( used_mib * 100 / total_mib ))

echo -e "${BOLD}GPU Memory${RESET}"
printf "  Total:  %6d MiB\n" "$total_mib"
printf "  Used:   %6d MiB  (%d%%)\n" "$used_mib" "$pct_used"
printf "  Free:   %6d MiB\n" "$free_mib"
echo ""

# --- Per-process breakdown ---
echo -e "${BOLD}Processes using GPU memory${RESET}"
GPU_PROCS=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory \
  --format=csv,noheader 2>/dev/null)

if [ -z "$GPU_PROCS" ]; then
  echo "  (none)"
else
  DISPLAY_MEM=0
  OTHER_MEM=0
  while IFS=',' read -r pid pname pmem; do
    pid=$(echo "$pid" | xargs)
    pname=$(echo "$pname" | xargs)
    pmem_val=$(echo "$pmem" | grep -oP '\d+')
    shortname=$(basename "$pname")

    # Detect display/compositor processes
    if echo "$pname" | grep -qiE 'Xorg|gnome|mutter|kwin|wayland|compositor|gdm|Xwayland'; then
      tag="[DISPLAY]"
      DISPLAY_MEM=$((DISPLAY_MEM + pmem_val))
      color="$YELLOW"
    else
      tag=""
      OTHER_MEM=$((OTHER_MEM + pmem_val))
      color="$RESET"
    fi
    printf "  ${color}PID %-7s  %-40s  %5s MiB  %s${RESET}\n" \
      "$pid" "$shortname" "$pmem_val" "$tag"
  done <<< "$GPU_PROCS"

  if [ "$DISPLAY_MEM" -gt 0 ]; then
    echo ""
    echo -e "  ${YELLOW}Display/compositor using ${DISPLAY_MEM} MiB — unplug monitors from RTX 5080${RESET}"
    echo -e "  ${YELLOW}(set iGPU as primary display in BIOS, then unplug from GPU)${RESET}"
  fi
fi
echo ""

# --- Required vs available ---
if [ "$MODEL" = "30b" ]; then
  REQUIRED=$MODEL_30B_TOTAL
  LABEL="30B-A3B UD-Q3_K_XL (NUM_PARALLEL=2)"
else
  REQUIRED=$MODEL_14B_TOTAL
  LABEL="14B Q4_K_M (NUM_PARALLEL=4)"
fi

HEADROOM=$((free_mib - REQUIRED))

echo -e "${BOLD}Headroom Analysis — ${LABEL}${RESET}"
printf "  Required:   %6d MiB  (weights + KV cache + overhead)\n" "$REQUIRED"
printf "  Available:  %6d MiB\n" "$free_mib"
printf "  Headroom:   %6d MiB\n" "$HEADROOM"
echo ""

if [ "$HEADROOM" -ge 2000 ]; then
  echo -e "  ${GREEN}✓ GO — plenty of headroom for a full overnight run${RESET}"
elif [ "$HEADROOM" -ge 500 ]; then
  echo -e "  ${YELLOW}⚠ MARGINAL — may work, but run soak test first and watch nvidia-smi${RESET}"
else
  echo -e "  ${RED}✗ NO GO — not enough free VRAM${RESET}"
  echo ""
  echo -e "  ${RED}Steps to free VRAM:${RESET}"
  echo "    1. Stop other Ollama/llama-server processes:"
  echo "       sudo systemctl stop ollama && sudo systemctl start ollama"
  echo "    2. Kill any other GPU processes shown above"
  echo "    3. Move display to iGPU (BIOS → primary display → integrated)"
  echo "       then unplug monitors from RTX 5080, plug into motherboard"
  echo "    4. Re-run this script"
fi
echo ""
