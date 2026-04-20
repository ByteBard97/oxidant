# Overnight Local Model Run — Runbook

Converts simple nodes (cyclomatic complexity ≤ 3) using a local Qwen model via Ollama
and the pi coding agent harness. Preserves Claude API quota for complex nodes.

---

## Hardware

| Machine | Role |
|---------|------|
| Linux box — Ryzen 9 7950X, RTX 5080 16GB, 64GB DDR5 | Inference server + run host |
| Your Mac | SSH control, monitoring |

---

## Model Strategy — Two-Tier Pipeline

**Tier 1 — Primary batch workhorse (4 parallel workers):**
```bash
ollama pull qwen2.5-coder:14b-instruct-q5_K_M
```
~10 GB weights, fits four parallel 8K-context workers with 5–6 GB headroom. ~55–70 tok/s
single-stream, ~6–8 s/node, 2.5× retry margin. Apache-2.0. Mature Ollama template,
no known bugs. **This is the default model for the overnight run.**

**Tier 2 — Quality fallback for `cargo check` retries:**
```bash
ollama pull hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q3_K_XL
```
13.8 GB weights, full-GPU resident on 16GB. Run at `NUM_PARALLEL=2` only. ~40–55 tok/s.
Unsloth's UD-Q3_K_XL stays within ~1 point of Q4_K_M quality per KL-divergence data.
Use this only for nodes that fail the 14B pass twice.

**Do NOT use:**
- `qwen3-coder:30b` (Q4_K_M = 19 GB — won't fit; measured at ~23 tok/s with CPU offload on RTX 5080, Ollama issue #14446)
- `qwen2.5-coder:32b` (15+ GB, at most 2 parallel workers)
- `deepseek-coder-v2:*` (double-BOS tokenizer bug, Ollama template unfixed — quietly degrades output)
- `qwen35moe` variants (Ollama issue #14510 forces PARALLEL=1, collapsing throughput)

---

## One-Time Setup (Linux machine)

### 1. Install Ollama (≥ 0.20.x)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Enable as a system service so it survives reboots:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

**Important: use Ollama ≥ 0.20.x.** Earlier Blackwell-era builds had sm_120 GPU discovery
regressions (issue #13163) and intermittent "0 B VRAM" detection (issue #13338).

### 2. Configure the Ollama daemon

Create `/etc/systemd/system/ollama.service.d/override.conf`:

```ini
[Service]
ExecStartPre=/bin/sleep 30
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_MAX_QUEUE=2048"
Environment="OLLAMA_LOAD_TIMEOUT=10m"
Environment="CUDA_VISIBLE_DEVICES=0"
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Why each setting matters:**

- `OLLAMA_FLASH_ATTENTION=1` — **Critical.** Off by default. KV-cache quantization silently
  does nothing without it (issue #13337). On 16 GB this is the difference between four
  parallel streams and OOM.

- `OLLAMA_KV_CACHE_TYPE=q8_0` — Use q8_0, not q4_0. q8_0 at +0.7% perplexity delta
  (negligible). q4_0 causes measurable code corruption and slows generation 12–37%
  at long contexts (llama.cpp discussion #20969).

- `OLLAMA_NUM_PARALLEL=4` — Four concurrent workers for the 14B tier. **Drop to 2**
  when switching to the 30B-A3B tier.

- `OLLAMA_CONTEXT_LENGTH=8192` — **Critical.** See Bug #14120 below. Never rely on
  auto-sizing.

- `OLLAMA_KEEP_ALIVE=24h` — Keep model loaded indefinitely. No reload cost between nodes.

- `CUDA_VISIBLE_DEVICES=0` — Ensures RTX 5080 is used as compute card. Pair with
  iGPU primary display in BIOS (see Headless GPU section).

### 3. Pull the models

```bash
# Tier 1 — always pull this
ollama pull qwen2.5-coder:14b-instruct-q5_K_M

# Tier 2 — pull before first overnight run (13.8 GB, from Hugging Face)
ollama pull hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q3_K_XL
```

Verify tier 1 loads correctly:

```bash
ollama run qwen2.5-coder:14b-instruct-q5_K_M "write a Rust hello world" --verbose
```

Should show ~55–70 tok/s with all layers on GPU.

### 4. Create the custom Modelfile

Build a pre-configured model so per-request options are baked in:

```bash
cd /path/to/oxidant
ollama create oxidant-worker-14b -f Modelfile.14b
```

Verify it works:

```bash
ollama run oxidant-worker-14b "fn add(a: i32, b: i32) -> i32 {"
```

### 5. Install pi coding agent

```bash
npm install -g @badlogic/pi-coding-agent
```

Configure Ollama as a provider — create `~/.pi/agent/models.json`:

```json
[
  {
    "id": "oxidant-worker-14b",
    "name": "Qwen2.5-Coder 14B Q5 (local, Oxidant tuned)",
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
```

Verify pi can reach the model:

```bash
pi --print --model "ollama/oxidant-worker-14b" "write a Rust hello world"
```

### 6. Install Oxidant dependencies

```bash
cd /path/to/oxidant
uv sync
```

---

## Known Bugs — Read Before Running

### Bug #14120 — context-length OOM at high parallelism

The auto-context-length logic in some Ollama versions does not divide by parallel count.
With `NUM_PARALLEL=4`, Ollama can allocate KV for 131K tokens on a model you thought
was running at 8K — causing silent OOM.

**Fix: always pass `num_ctx: 8192` explicitly with every request** (done in the Modelfile
and in `invoke_pi()`). Also set `OLLAMA_CONTEXT_LENGTH=8192` on the daemon. Never rely
on auto-sizing.

### Bug #14446 — Qwen3-Coder 30B Q4_K_M on RTX 5080

Confirmed measurement on an actual RTX 5080 (Ollama issue #14446): Qwen3-Coder 30B-A3B
Q4_K_M (19 GB) runs with 25/41 layers on GPU at ~23 tok/s. **This is why we use
Unsloth UD-Q3_K_XL (13.8 GB) instead** — full GPU residency, ~40–55 tok/s.

### Blackwell (RTX 5080) driver stability

Driver 570 + Qwen models have documented mid-batch hang reports (NVIDIA forum thread
341659). Consider upgrading to driver 580 via System76's repo. **Always run a soak
test before the overnight batch.**

---

## Soak Test (required before first overnight run)

Run a 50-node pilot to validate GPU residency, throughput, and cargo check pass rate:

```bash
# Start Ollama with the override config active
sudo systemctl restart ollama

# Watch GPU utilization in one terminal
watch -n5 nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.free --format=csv

# Run 50 simple nodes
uv run oxidant reset-stuck --db oxidant.db
uv run oxidant phase-b --config oxidant.local.config.json --db oxidant.db --limit 50
```

What to check:
- GPU memory.used should stay ≤ 15.5 GB (ideally ≤ 14 GB for headroom)
- utilization.gpu should stay ≥ 70% during inference
- Soak run should complete < 10 minutes at 4× parallel
- No "0 B VRAM" messages in `journalctl -u ollama -f`

If GPU utilization drops or memory spills, something is wrong with the config before
you commit 8 hours to it.

---

## Config File for Local Runs

Create `oxidant.local.config.json` alongside `oxidant.config.json`:

```json
{
  "target_repo": "corpora/msagl-rs",
  "source_repo": "corpora/msagljs",
  "backend": "local",
  "local_model": "oxidant-worker-14b",
  "complexity_max": 3,
  "parallelism": 4,
  "start_tier": "haiku",
  "max_attempts": { "haiku": 2 },
  "no_escalate": true,
  "crate_inventory": [],
  "architectural_decisions": {}
}
```

Copy the real `crate_inventory` and `architectural_decisions` from `oxidant.config.json`.

Notes:
- `local_model: "oxidant-worker-14b"` — uses the pre-configured Modelfile model.
- `complexity_max: 3` — only simple nodes (3,199 eligible). Harder nodes queued for Haiku API.
- `parallelism: 4` — four concurrent 14B workers.
- `no_escalate: true` — don't escalate to sonnet/opus, just queue for review.
- `max_attempts: 2` — two tries then move on.

---

## Before Each Run — Reset Stuck Nodes

If the previous run crashed, some nodes will be stuck as `IN_PROGRESS`. Reset them:

```bash
uv run oxidant reset-stuck --db oxidant.db
```

This resets all `IN_PROGRESS` nodes to `NOT_STARTED`. Safe to run even if no nodes
are stuck. Always run this before starting a new batch.

---

## The Run Script

Save as `run_overnight.sh` in the oxidant directory:

```bash
#!/usr/bin/env bash
set -euo pipefail

DB="oxidant.db"
CONFIG="oxidant.local.config.json"
LOG="overnight_$(date +%Y%m%d_%H%M%S).log"

echo "=== Oxidant overnight run starting at $(date) ===" | tee "$LOG"

# Reset any orphaned nodes from a previous crash
uv run oxidant reset-stuck --db "$DB" 2>&1 | tee -a "$LOG"

# Run until all simple nodes are done (or the machine was rebooted and restarted us)
while true; do
    echo "--- Starting batch at $(date) ---" | tee -a "$LOG"

    uv run oxidant phase-b \
        --config "$CONFIG" \
        --db "$DB" \
        2>&1 | tee -a "$LOG"

    EXIT_CODE=${PIPESTATUS[0]}

    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "=== Phase B completed cleanly at $(date) ===" | tee -a "$LOG"
        break
    else
        echo "=== Process exited with code $EXIT_CODE at $(date) — restarting in 30s ===" | tee -a "$LOG"
        # Reset stuck nodes before retry
        uv run oxidant reset-stuck --db "$DB" 2>&1 | tee -a "$LOG"
        sleep 30
    fi
done
```

```bash
chmod +x run_overnight.sh
```

---

## Crash / Reboot Failsafe — systemd Service

Create `/etc/systemd/system/oxidant-overnight.service`:

```ini
[Unit]
Description=Oxidant overnight local model run
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=geoff
WorkingDirectory=/path/to/oxidant
ExecStart=/path/to/oxidant/run_overnight.sh
Restart=on-failure
RestartSec=60
StandardOutput=append:/path/to/oxidant/overnight_service.log
StandardError=append:/path/to/oxidant/overnight_service.log

[Install]
WantedBy=multi-user.target
```

Enable it so it starts automatically on boot:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oxidant-overnight
```

**To start a run:**

```bash
sudo systemctl start oxidant-overnight
```

**To monitor:**

```bash
journalctl -u oxidant-overnight -f
# or
tail -f /path/to/oxidant/overnight_service.log
```

**To stop cleanly (waits for current node to finish):**

```bash
sudo systemctl stop oxidant-overnight
```

If the machine reboots overnight: Ollama auto-starts (enabled above), then
oxidant-overnight auto-starts (enabled above), `reset-stuck` runs first to
clean orphaned nodes, then the batch continues where it left off.

---

## Monitoring From Your Mac

```bash
# Live log tail
ssh geoff@192.168.0.200 "tail -f /path/to/oxidant/overnight_service.log"

# Quick status count
ssh geoff@192.168.0.200 "sqlite3 /path/to/oxidant/oxidant.db \
  'SELECT status, COUNT(*) FROM nodes GROUP BY status'"

# GPU utilization
ssh geoff@192.168.0.200 "watch -n5 nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.free --format=csv"
```

---

## Headless GPU Setup (recommended)

Unplugging monitors (or routing display through the AMD iGPU) eliminates display
scheduling conflicts on the RTX 5080. In BIOS/UEFI, set primary display adapter to
the integrated graphics. The RTX 5080 then runs as a pure compute card.

VRAM freed by the display is minimal (~100-200MB) but you avoid compositor interrupts
during CUDA inference. Also pairs with `CUDA_VISIBLE_DEVICES=0` in the daemon config
to ensure Ollama always targets the RTX 5080 even after iGPU is primary display.

---

## Performance Expectations

| Tier | Model | Weights | Parallel | Est tok/s | Sec/node | Nodes/8h |
|------|-------|---------|----------|-----------|----------|----------|
| 1 (primary) | 14B Q5_K_M | ~10 GB | 4 | 55–70 | 6–8s | 1,600–2,400 |
| 2 (fallback) | 30B-A3B UD-Q3_K_XL | ~13.8 GB | 2 | 40–55 | 10–12s | ~400–500 |

Tier 1 handles ~75% of nodes in the first pass. Tier 2 mops up cargo-check failures.

Simple nodes (cc ≤ 3): **3,199 total** → expect 2 nights at Tier 1 throughput.

After simple nodes are done, run medium/hard nodes against the Haiku API:

```bash
# Reset config back to claude backend, remove complexity_max
uv run oxidant phase-b --config oxidant.config.json --db oxidant.db
```

---

## Node Counts Reference (as of 2026-04-20)

| Status | Count |
|--------|-------|
| converted | 493 |
| human_review | 26 (reset these first) |
| not_started simple (cc ≤ 3) | 3,199 |
| not_started medium (cc 4–8) | 898 |
| not_started hard (cc > 8) | 204 |
| **Total remaining** | **4,327** |

Reset the 26 human_review nodes before starting (they failed before the pipeline was
fixed and should be retried):

```bash
sqlite3 oxidant.db "UPDATE nodes SET status='not_started' WHERE status='human_review'"
```
