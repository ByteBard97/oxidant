import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.agents.invoke import invoke_claude, invoke_pi


def _fake_popen(stdout: str, returncode: int = 0, stderr: str = "") -> MagicMock:
    """Return a mock Popen instance whose communicate() returns (stdout, stderr)."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.communicate.return_value = (stdout, stderr)
    mock.pid = 12345
    return mock


def test_strips_api_key(monkeypatch, tmp_path):
    """ANTHROPIC_API_KEY must be absent from the subprocess environment."""
    captured_env: dict = {}

    def fake_popen(cmd, *, env, **kwargs):
        captured_env.update(env)
        return _fake_popen('{"result": "fn foo() { 42 }"}')

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    with patch("oxidant.agents.invoke.subprocess.Popen", side_effect=fake_popen):
        result = invoke_claude("convert this", cwd=str(tmp_path))

    assert "ANTHROPIC_API_KEY" not in captured_env
    assert result == "fn foo() { 42 }"


def test_returns_result_field(tmp_path):
    """Extracts the 'result' field from the JSON response."""
    response_json = '{"result": "let x = 1;", "cost_usd": 0.001, "is_error": false}'
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen(response_json)):
        result = invoke_claude("prompt", cwd=str(tmp_path))
    assert result == "let x = 1;"


def test_raises_on_nonzero_exit(tmp_path):
    """RuntimeError raised when claude exits non-zero."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("", returncode=1, stderr="error message")):
        with pytest.raises(RuntimeError, match="exited 1"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_raises_on_non_json_output(tmp_path):
    """RuntimeError raised when output is not valid JSON."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("not json")):
        with pytest.raises(RuntimeError, match="non-JSON"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_raises_on_missing_result_key(tmp_path):
    """RuntimeError raised when JSON is valid but missing 'result'."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen('{"other_key": "value"}')):
        with pytest.raises(RuntimeError, match="missing 'result'"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_tier_haiku_uses_shorter_timeout(tmp_path):
    """Haiku tier gets a shorter timeout than opus."""
    # timeout is passed to proc.communicate(), not to Popen()
    communicate_kwargs: dict = {}

    def capture_communicate(**kwargs):
        communicate_kwargs.update(kwargs)
        return ('{"result": "x"}', "")

    mock_proc = _fake_popen('{"result": "x"}')
    mock_proc.communicate.side_effect = capture_communicate

    with patch("oxidant.agents.invoke.subprocess.Popen", return_value=mock_proc):
        invoke_claude("p", cwd=str(tmp_path), tier="haiku")
    haiku_timeout = communicate_kwargs["timeout"]

    mock_proc.communicate.side_effect = capture_communicate
    with patch("oxidant.agents.invoke.subprocess.Popen", return_value=mock_proc):
        invoke_claude("p", cwd=str(tmp_path), tier="opus")
    opus_timeout = communicate_kwargs["timeout"]

    assert haiku_timeout < opus_timeout


# ── invoke_pi ─────────────────────────────────────────────────────────────────

def _fake_popen(stdout: str, returncode: int = 0, stderr: str = "") -> MagicMock:
    """Return a mock Popen instance whose communicate() returns (stdout, stderr)."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.communicate.return_value = (stdout, stderr)
    mock.pid = 12345
    return mock


def test_invoke_pi_returns_response(tmp_path):
    """invoke_pi returns sanitized stdout from the pi process."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("fn foo() { 42 }")):
        result = invoke_pi("convert this", cwd=str(tmp_path))
    assert result == "fn foo() { 42 }"


def test_invoke_pi_raises_on_nonzero_exit(tmp_path):
    """RuntimeError raised when pi exits non-zero."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("", returncode=1, stderr="pi crashed")):
        with pytest.raises(RuntimeError, match="pi exited 1"):
            invoke_pi("prompt", cwd=str(tmp_path))


def test_invoke_pi_raises_on_empty_output(tmp_path):
    """RuntimeError raised when pi returns empty stdout."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("")):
        with pytest.raises(RuntimeError, match="empty output"):
            invoke_pi("prompt", cwd=str(tmp_path))


def test_invoke_pi_uses_ollama_model_flag(tmp_path):
    """The pi command includes --model ollama/<model>."""
    captured_cmd: list = []

    def capture_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _fake_popen("fn foo() {}")

    with patch("oxidant.agents.invoke.subprocess.Popen", side_effect=capture_popen):
        invoke_pi("prompt", cwd=str(tmp_path), model="qwen2.5-coder:14b")

    assert "--model" in captured_cmd
    model_idx = captured_cmd.index("--model")
    assert captured_cmd[model_idx + 1] == "ollama/qwen2.5-coder:14b"


def test_invoke_pi_local_timeout_longer_than_claude(tmp_path):
    """Local model timeouts are longer than Claude API timeouts for same tier."""
    from oxidant.agents.invoke import _TIMEOUT_BY_TIER, _LOCAL_TIMEOUT_BY_TIER
    assert _LOCAL_TIMEOUT_BY_TIER["haiku"] > _TIMEOUT_BY_TIER["haiku"]
    assert _LOCAL_TIMEOUT_BY_TIER["sonnet"] > _TIMEOUT_BY_TIER["sonnet"]


def test_invoke_pi_sanitizes_markdown_fences(tmp_path):
    """Markdown fences in pi output are stripped just like Claude output."""
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("```rust\nfn foo() { 1 }\n```")):
        result = invoke_pi("prompt", cwd=str(tmp_path))
    assert "```" not in result
    assert "fn foo() { 1 }" in result


def test_invoke_pi_writes_prompt_log(tmp_path):
    """When prompt_log_dir is set, prompt and response are written to disk."""
    log_dir = tmp_path / "logs"
    with patch("oxidant.agents.invoke.subprocess.Popen",
               return_value=_fake_popen("fn bar() {}")):
        invoke_pi("my prompt", cwd=str(tmp_path), prompt_log_dir=log_dir, label="test_node")

    assert (log_dir / "test_node_prompt.txt").read_text() == "my prompt"
    assert "fn bar()" in (log_dir / "test_node_response.txt").read_text()
