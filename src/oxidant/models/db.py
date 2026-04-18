"""SQLModel table definitions for Oxidant's SQLite backing store.

Two tables:
  - NodeRecord   — one row per conversion node (mirrors ConversionNode fields)
  - ManifestMeta — one row of manifest-level metadata (source_repo, version, etc.)

List and dict fields (parameter_types, type_dependencies, etc.) are stored as
JSON strings because they are always loaded as a whole unit — never queried
column-by-column. Fixed scalar fields (status, topological_order, tier, etc.)
are discrete columns so SQL can GROUP BY, ORDER BY, and WHERE on them cheaply.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Field, SQLModel


class NodeRecord(SQLModel, table=True):
    """One row per manifest node. Direct SQL equivalent of ConversionNode."""

    __tablename__ = "nodes"  # type: ignore[assignment]

    # ── Identity ───────────────────────────────────────────────────────────
    node_id:     str = Field(primary_key=True)
    source_file: str
    line_start:  int
    line_end:    int
    source_text: str
    node_kind:   str  # NodeKind enum value

    # ── Signature ──────────────────────────────────────────────────────────
    return_type:  Optional[str] = None
    parent_class: Optional[str] = None

    # ── Metrics ────────────────────────────────────────────────────────────
    cyclomatic_complexity: int = 1

    # ── Topology (computed by Phase A) ─────────────────────────────────────
    topological_order: Optional[int] = None
    bfs_level:         Optional[int] = None

    # ── Classification ─────────────────────────────────────────────────────
    tier:        Optional[str] = None  # TranslationTier enum value
    tier_reason: Optional[str] = None

    # ── Phase B progress (the columns written constantly) ──────────────────
    status:        str = "not_started"  # NodeStatus enum value
    snippet_path:  Optional[str] = None
    attempt_count: int = 0
    last_error:    Optional[str] = None

    # ── JSON-serialized compound fields ────────────────────────────────────
    # Stored as JSON strings; deserialized in to_conversion_node()
    parameter_types:   str = "{}"
    type_dependencies: str = "[]"
    call_dependencies: str = "[]"
    callers:           str = "[]"
    idioms_needed:     str = "[]"

    # ── Conversion helpers ─────────────────────────────────────────────────

    def to_conversion_node(self) -> "ConversionNode":  # noqa: F821
        """Return a ConversionNode pydantic model populated from this row."""
        from oxidant.models.manifest import ConversionNode, NodeKind, NodeStatus, TranslationTier

        return ConversionNode(
            node_id=self.node_id,
            source_file=self.source_file,
            line_start=self.line_start,
            line_end=self.line_end,
            source_text=self.source_text,
            node_kind=NodeKind(self.node_kind),
            return_type=self.return_type,
            parent_class=self.parent_class,
            cyclomatic_complexity=self.cyclomatic_complexity,
            topological_order=self.topological_order,
            bfs_level=self.bfs_level,
            tier=TranslationTier(self.tier) if self.tier else None,
            tier_reason=self.tier_reason,
            status=NodeStatus(self.status),
            snippet_path=self.snippet_path,
            attempt_count=self.attempt_count,
            last_error=self.last_error,
            parameter_types=json.loads(self.parameter_types),
            type_dependencies=json.loads(self.type_dependencies),
            call_dependencies=json.loads(self.call_dependencies),
            callers=json.loads(self.callers),
            idioms_needed=json.loads(self.idioms_needed),
        )

    @classmethod
    def from_conversion_node(cls, node: "ConversionNode") -> "NodeRecord":  # noqa: F821
        """Build a NodeRecord row from a ConversionNode pydantic model."""
        return cls(
            node_id=node.node_id,
            source_file=node.source_file,
            line_start=node.line_start,
            line_end=node.line_end,
            source_text=node.source_text,
            node_kind=node.node_kind.value,
            return_type=node.return_type,
            parent_class=node.parent_class,
            cyclomatic_complexity=node.cyclomatic_complexity,
            topological_order=node.topological_order,
            bfs_level=node.bfs_level,
            tier=node.tier.value if node.tier else None,
            tier_reason=node.tier_reason,
            status=node.status.value,
            snippet_path=node.snippet_path,
            attempt_count=node.attempt_count,
            last_error=node.last_error,
            parameter_types=json.dumps(node.parameter_types),
            type_dependencies=json.dumps(node.type_dependencies),
            call_dependencies=json.dumps(node.call_dependencies),
            callers=json.dumps(node.callers),
            idioms_needed=json.dumps(node.idioms_needed),
        )


class ManifestMeta(SQLModel, table=True):
    """Single-row table storing manifest-level metadata."""

    __tablename__ = "manifest_meta"  # type: ignore[assignment]

    id:           int = Field(default=1, primary_key=True)
    version:      str = "1.0"
    source_repo:  str = ""
    generated_at: str = ""
