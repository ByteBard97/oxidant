import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.agents.invoke import invoke_claude


def _fake_run(returncode: int, stdout: str, stderr: str = ""):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


def test_strips_api_key(monkeypatch, tmp_path):
    """ANTHROPIC_API_KEY must be absent from the subprocess environment."""
    captured_env: dict = {}

    def fake_run(cmd, *, env, **kwargs):
        captured_env.update(env)
        return _fake_run(0, '{"result": "fn foo() { 42 }"}')

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    with patch("oxidant.agents.invoke.subprocess.run", side_effect=fake_run):
        result = invoke_claude("convert this", cwd=str(tmp_path))

    assert "ANTHROPIC_API_KEY" not in captured_env
    assert result == "fn foo() { 42 }"


def test_returns_result_field(tmp_path):
    """Extracts the 'result' field from the JSON response."""
    response_json = '{"result": "let x = 1;", "cost_usd": 0.001, "is_error": false}'
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(0, response_json)):
        result = invoke_claude("prompt", cwd=str(tmp_path))
    assert result == "let x = 1;"


def test_raises_on_nonzero_exit(tmp_path):
    """RuntimeError raised when claude exits non-zero."""
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(1, "", "error message")):
        with pytest.raises(RuntimeError, match="exited 1"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_raises_on_non_json_output(tmp_path):
    """RuntimeError raised when output is not valid JSON."""
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(0, "not json")):
        with pytest.raises(RuntimeError, match="non-JSON"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_raises_on_missing_result_key(tmp_path):
    """RuntimeError raised when JSON is valid but missing 'result'."""
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(0, '{"other_key": "value"}')):
        with pytest.raises(RuntimeError, match="missing 'result'"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_tier_haiku_uses_shorter_timeout(tmp_path):
    """Haiku tier gets a shorter timeout than opus."""
    call_kwargs: dict = {}

    def capture_run(cmd, **kwargs):
        call_kwargs.update(kwargs)
        return _fake_run(0, '{"result": "x"}')

    with patch("oxidant.agents.invoke.subprocess.run", side_effect=capture_run):
        invoke_claude("p", cwd=str(tmp_path), tier="haiku")
    haiku_timeout = call_kwargs["timeout"]

    with patch("oxidant.agents.invoke.subprocess.run", side_effect=capture_run):
        invoke_claude("p", cwd=str(tmp_path), tier="opus")
    opus_timeout = call_kwargs["timeout"]

    assert haiku_timeout < opus_timeout
