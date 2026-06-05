#!/usr/bin/env bash
# setup.sh — one-time setup for the oxidant overnight run on this machine
# Run with sudo: sudo bash ./scripts/setup.sh
# Or without sudo to do only the non-privileged steps

set -euo pipefail

OXIDANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
OLLAMA_OVERRIDE="$OLLAMA_OVERRIDE_DIR/override.conf"
SERVICE_DEST="/etc/systemd/system/oxidant-overnight.service"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BOLD='\033[1m'; RESET='\033[0m'
NEED_SUDO=0

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; }
step() { echo -e "\n${BOLD}── $1 ──${RESET}"; }

HAS_SUDO=0
if [ "$EUID" -eq 0 ] || sudo -n true 2>/dev/null; then
  HAS_SUDO=1
fi

echo ""
echo -e "${BOLD}=== Oxidant Server Setup — $(date) ===${RESET}"
echo ""
[ "$HAS_SUDO" -eq 1 ] && echo -e "  Running with sudo access — will configure systemd services" \
                       || warn "No sudo — skipping systemd steps (run with sudo to complete)"

# ── PATH ─────────────────────────────────────────────────────────────────────
step "PATH"
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
  warn "~/.local/bin not in PATH for this shell"
  if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    ok "Added ~/.local/bin to ~/.bashrc (re-login or: source ~/.bashrc)"
  else
    ok "~/.local/bin already in ~/.bashrc"
  fi
fi
export PATH="$HOME/.local/bin:$PATH"

# ── uv ───────────────────────────────────────────────────────────────────────
step "uv (Python package manager)"
if command -v uv &>/dev/null; then
  ok "uv already installed: $(uv --version)"
else
  echo "  Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ok "uv installed"
fi

# ── pi coding agent ───────────────────────────────────────────────────────────
step "pi coding agent"
if [ -x "$HOME/tools/pi/pi" ] && command -v pi &>/dev/null; then
  ok "pi already installed"
else
  echo "  Downloading pi v0.67.68..."
  cd /tmp
  curl -L -o pi-linux-x64.tar.gz \
    https://github.com/badlogic/pi-mono/releases/download/v0.67.68/pi-linux-x64.tar.gz
  rm -rf "$HOME/tools/pi"
  mkdir -p "$HOME/tools"
  tar xzf pi-linux-x64.tar.gz -C "$HOME/tools/"

  cat > "$HOME/.local/bin/pi" << 'WRAPPER'
#!/usr/bin/env bash
exec ~/tools/pi/pi "$@"
WRAPPER
  chmod +x "$HOME/.local/bin/pi"
  ok "pi installed at ~/tools/pi/pi (wrapper at ~/.local/bin/pi)"
fi

# ── pi models config ──────────────────────────────────────────────────────────
step "pi agent model config"
mkdir -p "$HOME/.pi/agent"
cat > "$HOME/.pi/agent/models.json" << 'EOF'
[
  {
    "id": "oxidant-worker-14b",
    "name": "Qwen2.5-Coder 14B Q4 (local, Oxidant tuned)",
    "api": "openai-completions",
    "provider": "ollama",
    "baseUrl": "http://localhost:11434/v1",
    "compat": { "supportsDeveloperRole": false },
    "reasoning": false,
    "input": ["text"],
    "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
    "contextWindow": 8192,
    "maxTokens": 1024
  }
]
EOF
ok "~/.pi/agent/models.json written"

# ── oxidant repo ──────────────────────────────────────────────────────────────
step "Oxidant repo and dependencies"
if [ -d "$OXIDANT_DIR/.git" ]; then
  ok "Oxidant repo present at $OXIDANT_DIR"
  cd "$OXIDANT_DIR" && uv sync --quiet && ok "Python dependencies up to date"
else
  fail "Oxidant not at $OXIDANT_DIR — clone it first:"
  echo "  cd ~/projects && git clone https://github.com/ByteBard97/oxidant.git"
fi

# ── oxidant-worker-14b model ──────────────────────────────────────────────────
step "oxidant-worker-14b Ollama model"
if ollama list 2>/dev/null | grep -q "oxidant-worker-14b"; then
  ok "oxidant-worker-14b already created"
else
  if ollama list 2>/dev/null | grep -q "qwen2.5-coder:14b"; then
    echo "  Building from existing qwen2.5-coder:14b..."
    ollama create oxidant-worker-14b -f "$OXIDANT_DIR/Modelfile.14b" && ok "oxidant-worker-14b created"
  else
    echo "  Pulling qwen2.5-coder:14b (9 GB)..."
    ollama pull qwen2.5-coder:14b
    ollama create oxidant-worker-14b -f "$OXIDANT_DIR/Modelfile.14b" && ok "oxidant-worker-14b created"
  fi
fi

# ── Ollama daemon config (needs sudo) ─────────────────────────────────────────
step "Ollama daemon configuration (requires sudo)"
if [ "$HAS_SUDO" -eq 0 ]; then
  warn "Skipped — re-run with sudo to apply"
  NEED_SUDO=1
else
  sudo mkdir -p "$OLLAMA_OVERRIDE_DIR"
  sudo tee "$OLLAMA_OVERRIDE" > /dev/null << 'EOF'
[Service]
ExecStartPre=/bin/sleep 30
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_MAX_QUEUE=2048"
Environment="OLLAMA_LOAD_TIMEOUT=10m"
Environment="CUDA_VISIBLE_DEVICES=0"
EOF
  ok "Ollama override.conf written"
  sudo systemctl daemon-reload
  sudo systemctl restart ollama
  sleep 5
  systemctl is-active --quiet ollama && ok "Ollama restarted with new config" || fail "Ollama failed to restart"
fi

# ── oxidant-overnight systemd service (needs sudo) ────────────────────────────
step "oxidant-overnight systemd service (requires sudo)"
if [ "$HAS_SUDO" -eq 0 ]; then
  warn "Skipped — re-run with sudo to apply"
  NEED_SUDO=1
else
  sudo cp "$OXIDANT_DIR/oxidant-overnight.service" "$SERVICE_DEST"
  sudo systemctl daemon-reload
  sudo systemctl enable oxidant-overnight
  ok "oxidant-overnight.service installed and enabled (starts on boot)"
  echo "  To start a run: sudo systemctl start oxidant-overnight"
fi

# ── run_overnight.sh ──────────────────────────────────────────────────────────
step "run_overnight.sh"
if [ -x "$OXIDANT_DIR/run_overnight.sh" ]; then
  ok "run_overnight.sh present and executable"
else
  fail "run_overnight.sh missing or not executable — check oxidant repo"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}=== Setup Complete ===${RESET}"
echo ""
if [ "$NEED_SUDO" -eq 1 ]; then
  echo -e "  ${YELLOW}Some steps were skipped — re-run with sudo to finish:${RESET}"
  echo "    sudo bash $OXIDANT_DIR/scripts/setup.sh"
  echo ""
fi
echo "  Next steps:"
echo "    1. Move display to iGPU in BIOS, unplug monitors from RTX 5080"
echo "    2. ./scripts/check_vram.sh       ← verify VRAM is free"
echo "    3. ./scripts/smoke_test.sh       ← run end-to-end test"
echo "    4. sudo systemctl start oxidant-overnight"
echo ""
