"""Invoke Claude Code CLI as a subprocess for Phase B node translation.

IMPORTANT: Always strips ANTHROPIC_API_KEY from the environment before invoking.
If the key is present, Claude Code bills to the API account instead of the user's
Max subscription — this has caused accidental charges of $1,800+ for other users.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT_BY_TIER: dict[str, int] = {
    "haiku": 300,
    "sonnet": 600,
    "opus": 900,
}
_DEFAULT_TIMEOUT = 600
_MAX_PROMPT_LOG_CHARS = 200

# Local model timeouts are longer — inference is slower and cargo check still runs
_LOCAL_TIMEOUT_BY_TIER: dict[str, int] = {
    "haiku": 600,
    "sonnet": 900,
    "opus": 1200,
}


def invoke_claude(
    prompt: str,
    cwd: str | Path,
    tier: str = "sonnet",
    model: str | None = None,
    prompt_log_dir: Path | None = None,
    label: str = "",
) -> str:
    """Call ``claude --print --output-format json`` and return the response text.

    Args:
        prompt: The full conversion prompt to send to the model.
        cwd: Working directory for the subprocess (skeleton project root).
        tier: Translation tier — controls the timeout ("haiku" | "sonnet" | "opus").
        model: Explicit model ID (e.g. "claude-haiku-4-5-20251001"). If None,
               uses the Claude Code default model.
        prompt_log_dir: If set, write prompt and response to files here for debugging.
        label: File name prefix for prompt logs (e.g. "node_id__attempt1").

    Returns:
        The assistant's response text (value of the ``result`` key in the JSON).

    Raises:
        RuntimeError: claude exits non-zero, returns non-JSON, or ``result`` is absent.
        subprocess.TimeoutExpired: Call exceeds the tier-specific timeout.
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # CRITICAL: force Max subscription auth

    timeout = _TIMEOUT_BY_TIER.get(tier, _DEFAULT_TIMEOUT)
    logger.debug(
        "invoke_claude tier=%s model=%s prompt[:200]=%r",
        tier,
        model,
        prompt[:_MAX_PROMPT_LOG_CHARS],
    )

    if prompt_log_dir and label:
        log_dir = Path(prompt_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        safe_label = label.replace("/", "_").replace(":", "_")
        (log_dir / f"{safe_label}_prompt.txt").write_text(prompt)

    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--dangerously-skip-permissions",
    ]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)

    # Use start_new_session=True so the subprocess gets its own process group.
    # This lets us kill the entire group (claude + any cargo/bash children) on timeout,
    # preventing the 6-hour hang we hit when grandchildren kept pipes open.
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        raise

    returncode = proc.returncode

    if returncode != 0:
        # Claude often returns error JSON to stdout, not stderr
        detail = stderr.strip() or stdout.strip()
        # Try to extract a meaningful message from JSON error responses
        try:
            err_data = json.loads(stdout)
            if err_data.get("is_error") or err_data.get("type") == "error":
                detail = err_data.get("result") or err_data.get("error", {}).get("message") or detail
        except (json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError(
            f"claude exited {returncode}: {detail[:600]}"
        )

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude returned non-JSON output: {stdout[:200]}"
        ) from exc

    if "result" not in data:
        raise RuntimeError(
            f"claude JSON missing 'result' key: {list(data.keys())}"
        )

    raw_response = str(data["result"])
    if prompt_log_dir and label:
        log_dir = Path(prompt_log_dir)
        safe_label = label.replace("/", "_").replace(":", "_")
        (log_dir / f"{safe_label}_response.txt").write_text(raw_response)

    return _sanitize_snippet(raw_response)


def invoke_pi(
    prompt: str,
    cwd: str | Path,
    tier: str = "haiku",
    model: str = "qwen2.5-coder:32b",
    prompt_log_dir: Path | None = None,
    label: str = "",
) -> str:
    """Call the pi coding agent CLI with a local Ollama model and return the response.

    Pi is a minimal agentic harness (github.com/badlogic/pi-mono) that provides
    Read/Edit/Bash tools for any OpenAI-compatible backend. Use this instead of
    invoke_claude() to run against a local model without spending API quota.

    Args:
        prompt: The full conversion prompt.
        cwd: Working directory for the subprocess (workspace root).
        tier: Translation tier — controls the timeout.
        model: Ollama model tag (e.g. "qwen2.5-coder:32b").
        prompt_log_dir: If set, write prompt and response to files here.
        label: File name prefix for prompt logs.

    Returns:
        The assistant's final response text (sanitized).

    Raises:
        RuntimeError: pi exits non-zero or returns empty output.
        subprocess.TimeoutExpired: Call exceeds the tier-specific timeout.
    """
    timeout = _LOCAL_TIMEOUT_BY_TIER.get(tier, _DEFAULT_TIMEOUT)

    if prompt_log_dir and label:
        log_dir = Path(prompt_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        safe_label = label.replace("/", "_").replace(":", "_")
        (log_dir / f"{safe_label}_prompt.txt").write_text(prompt)

    cmd = [
        "pi",
        "--print",
        "--model", f"ollama/{model}",
        prompt,
    ]

    logger.debug("invoke_pi model=%s tier=%s prompt[:200]=%r", model, tier, prompt[:_MAX_PROMPT_LOG_CHARS])

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        raise

    if proc.returncode != 0:
        detail = stderr.strip() or stdout.strip()
        raise RuntimeError(f"pi exited {proc.returncode}: {detail[:600]}")

    if not stdout.strip():
        raise RuntimeError("pi returned empty output")

    raw_response = stdout.strip()
    if prompt_log_dir and label:
        log_dir = Path(prompt_log_dir)
        safe_label = label.replace("/", "_").replace(":", "_")
        (log_dir / f"{safe_label}_response.txt").write_text(raw_response)

    return _sanitize_snippet(raw_response)


_RUST_CODE_START_RE = re.compile(
    r"""^\s*(
        if\s | let\s | match\s | for\s | while\s | loop\b | return\b |
        \{ | \} | // | /\* | self\. | fn\s | pub\s | use\s |
        impl\s | struct\s | [0-9] | "
    )""",
    re.VERBOSE,
)


def _strip_prose_prefix(text: str) -> str:
    """Remove leading English prose from an agent response, keeping only the code.

    Agents often prefix their snippet with phrases like "Cargo check passed.
    Here is the function body:" followed by the actual code. We detect the
    first line that looks like Rust and return everything from there.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if _RUST_CODE_START_RE.match(line):
            # Include any blank lines immediately before the code start
            start = i
            while start > 0 and not lines[start - 1].strip():
                start -= 1
            return "\n".join(lines[start:])
    return text  # No prose detected — return unchanged


def _sanitize_snippet(text: str) -> str:
    """Strip markdown fences, prose prefix, and any character that would break cargo check.

    Rust source must be pure ASCII (outside of string/char literals, which the
    agent should not be producing anyway). Strip everything that isn't valid.
    """
    # Strip markdown code fences (```rust ... ``` or ``` ... ```)
    fenced = text.strip()
    if fenced.startswith("```"):
        lines = fenced.split("\n")
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner)
    else:
        # No markdown fence — strip any leading prose ("Here is the code:" etc.)
        text = _strip_prose_prefix(text)

    # Replace common unicode punctuation with ASCII equivalents first
    text = (
        text
        .replace("\u2014", "--")   # em-dash
        .replace("\u2013", "-")    # en-dash
        .replace("\u2018", "'")    # left single quote
        .replace("\u2019", "'")    # right single quote
        .replace("\u201c", '"')    # left double quote
        .replace("\u201d", '"')    # right double quote
        .replace("\u2026", "...")  # ellipsis
    )

    # Strip backticks — agents use them for markdown inline code (e.g. `foo`)
    # which is not valid Rust syntax outside raw string literals
    text = text.replace("`", "")

    # Strip any remaining non-ASCII characters — they have no place in Rust source
    text = text.encode("ascii", errors="ignore").decode("ascii")

    return text
