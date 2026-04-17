"""Assemble converted Rust snippet files into full module .rs files.

When all functional nodes (CONSTRUCTOR / METHOD / GETTER / SETTER / FREE_FUNCTION)
in a module are CONVERTED, this module replaces the skeleton's stub .rs file with
one that inlines each snippet, preceded by the node ID as a comment.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, NodeStatus, _STRUCTURAL_KINDS

logger = logging.getLogger(__name__)

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
    """Permanently replace all todo!() markers in the skeleton .rs file with
    their translated snippet bodies.

    This is the final "commit" step — the same injection verify.py does
    per-node during Phase B, but applied permanently for all CONVERTED nodes
    in the module at once.

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

    content = rs_path.read_text()
    replaced = 0

    for node in functional:
        marker = f'todo!("OXIDANT: not yet translated — {node.node_id}")'
        if marker not in content:
            logger.warning("Marker not found for %s in %s", node.node_id, rs_path.name)
            continue
        snippet = _load_snippet(node)
        if snippet is None:
            logger.warning("Missing snippet for CONVERTED node %s", node.node_id)
            continue
        content = content.replace(marker, snippet.strip(), 1)
        replaced += 1

    rs_path.write_text(content)
    logger.info("Assembled %s (%d/%d nodes replaced)", rs_path.name, replaced, len(functional))
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
