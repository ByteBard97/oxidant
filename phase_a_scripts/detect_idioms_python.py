#!/usr/bin/env python3
"""Phase A2 for Python sources: tag idioms on an existing manifest.

Reads conversion_manifest.json, walks each node's source_text with ast,
appends detected idioms to idioms_needed, writes manifest back in place.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def _detect_idioms(
    source_text: str,
    param_types: dict,
    return_type: str | None = None,
) -> list[str]:
    """Return list of idiom tags for a single node's source text."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []

    idioms: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
            idioms.add("list_comprehension")
        if isinstance(node, (ast.GeneratorExp, ast.Yield, ast.YieldFrom)):
            idioms.add("generator_function")
        if isinstance(node, ast.JoinedStr):
            idioms.add("format_string")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "isinstance":
                idioms.add("isinstance_check")
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comp, ast.Constant) and comp.value is None:
                    idioms.add("none_check")

    # Check only annotation strings (params + return type), NOT the full source_text
    # body — scanning source_text would produce false positives from comments/docstrings.
    annotation_strs = [t for t in param_types.values() if t] + ([return_type] if return_type else [])
    for t in annotation_strs:
        if "Optional[" in t or "| None" in t or "None |" in t:
            idioms.add("optional_type")

    if return_type and ("tuple[" in return_type or "Tuple[" in return_type):
        idioms.add("multiple_return")

    return sorted(idioms)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    nodes = manifest.get("nodes", {})

    tagged = 0
    for node in nodes.values():
        existing = set(node.get("idioms_needed", []))
        detected = _detect_idioms(
            node.get("source_text", ""),
            node.get("parameter_types", {}),
            return_type=node.get("return_type"),
        )
        node["idioms_needed"] = sorted(existing | set(detected))
        if detected:
            tagged += 1

    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Tagged idioms on {tagged}/{len(nodes)} nodes → {manifest_path}")


if __name__ == "__main__":
    main()
