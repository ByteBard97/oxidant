from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, TranslationTier
from oxidant.analysis.classify_tiers import classify_manifest


def _node(node_id: str, complexity: int = 1, idioms: list[str] | None = None) -> ConversionNode:
    return ConversionNode(
        node_id=node_id, source_file="x.ts", line_start=1, line_end=5,
        source_text="function foo() { return 1; }",
        node_kind=NodeKind.FREE_FUNCTION,
        parameter_types={}, return_type="number",
        type_dependencies=[], call_dependencies=[], callers=[],
        cyclomatic_complexity=complexity,
        idioms_needed=idioms or [],
    )


def _manifest(nodes: dict) -> Manifest:
    return Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)


@patch("oxidant.analysis.classify_tiers.anthropic.Anthropic")
def test_simple_node_classified_haiku(mock_cls, tmp_path):
    mock_cls.return_value.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"tier": "haiku", "reason": "simple getter"}')]
    )
    m = _manifest({"x__foo": _node("x__foo", complexity=1)})
    p = tmp_path / "manifest.json"
    m.save(p)
    classify_manifest(p, model="claude-haiku-4-5-20251001")
    assert Manifest.load(p).nodes["x__foo"].tier == TranslationTier.HAIKU


@patch("oxidant.analysis.classify_tiers.anthropic.Anthropic")
def test_complex_node_classified_opus(mock_cls, tmp_path):
    mock_cls.return_value.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"tier": "opus", "reason": "cyclic references"}')]
    )
    m = _manifest({"x__hard": _node("x__hard", complexity=20,
                                    idioms=["class_inheritance", "mutable_shared_state", "closure_capture"])})
    p = tmp_path / "manifest.json"
    m.save(p)
    classify_manifest(p, model="claude-haiku-4-5-20251001")
    result = Manifest.load(p).nodes["x__hard"]
    assert result.tier == TranslationTier.OPUS
    assert result.tier_reason


@patch("oxidant.analysis.classify_tiers.anthropic.Anthropic")
def test_invalid_json_falls_back_to_sonnet(mock_cls, tmp_path):
    mock_cls.return_value.messages.create.return_value = MagicMock(
        content=[MagicMock(text="not json")]
    )
    m = _manifest({"x__foo": _node("x__foo")})
    p = tmp_path / "manifest.json"
    m.save(p)
    classify_manifest(p, model="claude-haiku-4-5-20251001")
    assert Manifest.load(p).nodes["x__foo"].tier == TranslationTier.SONNET
