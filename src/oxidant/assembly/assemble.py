"""Assemble converted Rust snippet files into full module .rs files.

When all functional nodes (CONSTRUCTOR / METHOD / GETTER / SETTER / FREE_FUNCTION)
in a module are CONVERTED, this module replaces the skeleton's stub .rs file with
one that inlines each snippet, preceded by the node ID as a comment.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, NodeStatus

logger = logging.getLogger(__name__)

_STRUCTURAL_KINDS: frozenset[NodeKind] = frozenset({
    NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS,
})

_SNIPPET_KIND_ORDER: list[NodeKind] = [
    NodeKind.CONSTRUCTOR,
    NodeKind.METHOD,
    NodeKind.GETTER,
    NodeKind.SETTER,
    NodeKind.FREE_FUNCTION,
]

_FILE_HEADER = """\
#![allow(dead_code, unused_variables, unused_imports, non_snake_case)]
use std::rc::Rc;
use std::cell::RefCell;
use std::collections::{{HashMap, HashSet}};
"""


def _load_snippet(node: ConversionNode) -> str | None:
    if not node.snippet_path:
        return None
    p = Path(node.snippet_path)
    if not p.exists():
        logger.warning("Snippet file not found: %s", node.snippet_path)
        return None
    return p.read_text()


def assemble_module(
    module: str,
    nodes: list[ConversionNode],
    target_path: Path,
) -> bool:
    """Replace the skeleton .rs file with assembled snippet content.

    Returns True if assembly succeeded (all functional nodes CONVERTED),
    False if any functional node is not yet ready.
    """
    functional = [n for n in nodes if n.node_kind not in _STRUCTURAL_KINDS]
    if any(n.status != NodeStatus.CONVERTED for n in functional):
        return False

    rs_path = target_path / "src" / f"{module}.rs"
    if not rs_path.exists():
        logger.warning("Skeleton file not found: %s", rs_path)
        return False

    lines: list[str] = [_FILE_HEADER]

    for kind in _SNIPPET_KIND_ORDER:
        kind_nodes = sorted(
            (n for n in nodes if n.node_kind == kind),
            key=lambda n: n.topological_order or 0,
        )
        for node in kind_nodes:
            snippet = _load_snippet(node)
            if snippet is None:
                lines.append(f"// OXIDANT: missing snippet — {node.node_id}")
                continue
            lines.append(f"// ── {node.node_id} ──")
            lines.append(snippet.strip())
            lines.append("")

    rs_path.write_text("\n".join(lines) + "\n")
    logger.info("Assembled %s (%d functional nodes)", rs_path.name, len(functional))
    return True


def _module_name(source_file: str) -> str:
    from oxidant.analysis.generate_skeleton import _module_name as _gen
    return _gen(source_file)


def check_and_assemble(manifest: Manifest, target_path: Path) -> list[str]:
    """Assemble all modules whose functional nodes are fully CONVERTED.

    Returns the list of module names that were successfully assembled.
    """
    by_module: dict[str, list[ConversionNode]] = defaultdict(list)
    for node in manifest.nodes.values():
        by_module[_module_name(node.source_file)].append(node)

    assembled: list[str] = []
    for module, nodes in sorted(by_module.items()):
        if assemble_module(module, nodes, target_path):
            assembled.append(module)

    return assembled
