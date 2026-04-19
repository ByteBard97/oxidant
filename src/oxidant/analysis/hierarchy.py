"""TypeScript class hierarchy detection and classification for skeleton generation.

Two kinds of hierarchies in msagl-js:

  Category A — Discriminated unions (SweepEvent, VertexEvent, ConeSide, ...):
    Each subclass adds 0-3 unique fields; TS code dispatches via `instanceof`.
    Rust representation: pub enum Base { Variant1, Variant2 { fields }, ... }
    Child class .rs files get no struct — their variants live in the base enum.

  Category B — Behavior hierarchies (Algorithm, Attribute, ...):
    Each subclass is a large independent class sharing a base.
    Rust representation: pub struct Child { pub base: crate::parent::Parent, ... }

Classification is hardcoded from msagl-rust cross-validation, not pure heuristic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

HierarchyKind = Literal["enum", "struct"]

_EXTENDS_RE = re.compile(r'\bclass\s+\w+(?:\s*<[^>]*>)?\s+extends\s+(\w+)')
_CLASS_NAME_RE = re.compile(r'\bclass\s+(\w+)')

# Validated against msagl-rust reference port and field-count heuristic.
# "enum" = emit as pub enum variant in base file; skip child class structs.
# "struct" = child classes get pub base: crate::parent::Parent as first field.
KNOWN_HIERARCHIES: dict[str, HierarchyKind] = {
    # ── Discriminated unions → enum ────────────────────────────────────────
    # Only pure event/signal dispatch hierarchies where children are NOT used
    # as standalone named types elsewhere in the codebase.
    #
    # msagl-rust event_queue.rs confirms SweepEvent as pub enum.
    "SweepEvent": "enum",
    # Sub-hierarchies of SweepEvent — each gets its own enum, wrapped by parent.
    "VertexEvent": "enum",
    "BasicVertexEvent": "enum",
    # BasicReflectionEvent is a SweepEvent child AND itself an enum base.
    # Its children (HighReflectionEvent, LowReflectionEvent) are pure events.
    "BasicReflectionEvent": "enum",
    # Layer variants are dispatch-only in the layout engine.
    "Layer": "enum",
    # OptimalPacking variants have 0 fields — pure discriminants.
    "OptimalPacking": "enum",
    # ── Behavior hierarchies → struct composition ──────────────────────────
    # Children keep their own struct; get pub base: crate::parent::Parent field.
    "Algorithm": "struct",        # 24 subclasses, each a large independent class
    "Attribute": "struct",        # 4 subclasses, avg 22.5 fields each
    "SegmentBase": "struct",
    "LineSweeperBase": "struct",
    "GeomObject": "struct",
    "BasicGraphOnEdges": "struct",
    # These have small child field counts but their children ARE used as
    # standalone types in method signatures throughout the codebase.
    # Struct composition is the safe choice here.
    "Entity": "struct",           # Node/Edge/Graph used everywhere as distinct types
    "Port": "struct",             # CurvePort/FloatingPort used as distinct port types
    "DrawingObject": "struct",    # DrawingNode/DrawingEdge/DrawingGraph used standalone
    "SvgViewerObject": "struct",  # SvgViewerNode/SvgViewerEdge used standalone
    "GeomObject": "struct",       # GeomNode/GeomEdge used standalone
    "ObstacleSide": "struct",     # LeftObstacleSide/RightObstacleSide used standalone
    "BasicObstacleSide": "struct",# HighObstacleSide/LowObstacleSide referenced in events
    "ConeSide": "struct",         # ConeLeftSide/ConeRightSide used in sweep event fields
    "VisibilityEdge": "struct",   # AxisEdge (child) used as field type in sweep events
    "KdNode": "struct",
    "Packing": "struct",
}


@dataclass
class ClassInfo:
    class_name: str
    parent_name: str | None
    source_file: str
    node_id: str
    children: list[str] = field(default_factory=list)  # direct child class names


@dataclass
class HierarchyMap:
    by_name: dict[str, ClassInfo]
    # class_name → ConversionNode for field extraction
    nodes_by_class: dict[str, ConversionNode]

    def classify_base(self, class_name: str) -> HierarchyKind | None:
        """Return the hierarchy kind IF this class is a known hierarchy BASE.

        Returns None if this class is not a hierarchy base (it may still be a child).
        """
        return KNOWN_HIERARCHIES.get(class_name)

    def classify_as_child(self, class_name: str) -> tuple[str, HierarchyKind] | None:
        """If this class is a child of a known hierarchy, return (parent_name, kind).

        Returns None if this class has no known-hierarchy parent.
        """
        info = self.by_name.get(class_name)
        if not info or not info.parent_name:
            return None
        parent = info.parent_name
        kind = KNOWN_HIERARCHIES.get(parent)
        if kind:
            return (parent, kind)
        # Check grandparent (one level up for nested hierarchies like BasicVertexEvent)
        parent_info = self.by_name.get(parent)
        if parent_info and parent_info.parent_name:
            gp_kind = KNOWN_HIERARCHIES.get(parent_info.parent_name)
            if gp_kind:
                # e.g. LowBendVertexEvent → BasicVertexEvent → VertexEvent(enum)
                # The direct parent (BasicVertexEvent) is also in KNOWN_HIERARCHIES
                return (parent, KNOWN_HIERARCHIES.get(parent, gp_kind))
        return None

    def parent_of(self, class_name: str) -> str | None:
        info = self.by_name.get(class_name)
        return info.parent_name if info else None

    def children_of(self, class_name: str) -> list[str]:
        info = self.by_name.get(class_name)
        return info.children if info else []

    def source_file_of(self, class_name: str) -> str | None:
        info = self.by_name.get(class_name)
        return info.source_file if info else None

    def node_for(self, class_name: str) -> ConversionNode | None:
        return self.nodes_by_class.get(class_name)


def build_hierarchy_map(manifest: Manifest) -> HierarchyMap:
    """Scan all CLASS nodes in the manifest and build the full hierarchy map."""
    by_name: dict[str, ClassInfo] = {}
    nodes_by_class: dict[str, ConversionNode] = {}

    for node in manifest.nodes.values():
        if node.node_kind != NodeKind.CLASS:
            continue
        name_m = _CLASS_NAME_RE.search(node.source_text[:300])
        if not name_m:
            continue
        class_name = name_m.group(1)

        ext_m = _EXTENDS_RE.search(node.source_text[:300])
        parent_name = ext_m.group(1) if ext_m else None

        by_name[class_name] = ClassInfo(
            class_name=class_name,
            parent_name=parent_name,
            source_file=node.source_file,
            node_id=node.node_id,
        )
        nodes_by_class[class_name] = node

    # Populate children lists
    for info in by_name.values():
        if info.parent_name and info.parent_name in by_name:
            by_name[info.parent_name].children.append(info.class_name)

    return HierarchyMap(by_name=by_name, nodes_by_class=nodes_by_class)
