"""Invoke Claude Code CLI as a subprocess for Phase B node translation.

IMPORTANT: Always strips ANTHROPIC_API_KEY from the environment before invoking.
If the key is present, Claude Code bills to the API account instead of the user's
Max subscription — this has caused accidental charges of $1,800+ for other users.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT_BY_TIER: dict[str, int] = {
    "haiku": 120,
    "sonnet": 240,
    "opus": 360,
}
_DEFAULT_TIMEOUT = 300
_MAX_PROMPT_LOG_CHARS = 200


def invoke_claude(
    prompt: str,
    cwd: str | Path,
    tier: str = "sonnet",
    model: str | None = None,
) -> str:
    """Call ``claude --print --output-format json`` and return the response text.

    Args:
        prompt: The full conversion prompt to send to the model.
        cwd: Working directory for the subprocess (skeleton project root).
        tier: Translation tier — controls the timeout ("haiku" | "sonnet" | "opus").
        model: Explicit model ID (e.g. "claude-haiku-4-5-20251001"). If None,
               uses the Claude Code default model.

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

    cmd = ["claude", "--print", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)

    result = subprocess.run(
        cmd,
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude exited {result.returncode}:\n{result.stderr[:500]}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude returned non-JSON output: {result.stdout[:200]}"
        ) from exc

    if "result" not in data:
        raise RuntimeError(
            f"claude JSON missing 'result' key: {list(data.keys())}"
        )

    return str(data["result"])
