from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    CLASS = "class"
    CONSTRUCTOR = "constructor"
    METHOD = "method"
    GETTER = "getter"
    SETTER = "setter"
    FREE_FUNCTION = "free_function"
    INTERFACE = "interface"
    ENUM = "enum"
    TYPE_ALIAS = "type_alias"


class NodeStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    CONVERTED = "converted"
    FAILED = "failed"
    HUMAN_REVIEW = "human_review"


class TranslationTier(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class ConversionNode(BaseModel):
    node_id: str
    source_file: str
    line_start: int
    line_end: int
    source_text: str
    node_kind: NodeKind

    parameter_types: dict[str, str] = Field(default_factory=dict)
    return_type: Optional[str] = None

    type_dependencies: list[str] = Field(default_factory=list)
    call_dependencies: list[str] = Field(default_factory=list)
    callers: list[str] = Field(default_factory=list)

    parent_class: Optional[str] = None
    cyclomatic_complexity: int = 1
    idioms_needed: list[str] = Field(default_factory=list)

    topological_order: Optional[int] = None
    bfs_level: Optional[int] = None

    tier: Optional[TranslationTier] = None
    tier_reason: Optional[str] = None

    status: NodeStatus = NodeStatus.NOT_STARTED
    snippet_path: Optional[str] = None
    attempt_count: int = 0
    last_error: Optional[str] = None


_STRUCTURAL_KINDS: frozenset[NodeKind] = frozenset({
    NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS,
})


class Manifest(BaseModel):
    version: str = "1.0"
    source_repo: str
    generated_at: str
    nodes: dict[str, ConversionNode] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        return cls.model_validate_json(path.read_text())

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2))

    def eligible_nodes(self) -> list[ConversionNode]:
        """NOT_STARTED nodes whose every in-manifest dependency is CONVERTED.

        Dependencies referencing node IDs outside this manifest are ignored —
        they represent unexported or cross-repo code not extracted by Phase A.
        """
        manifest_ids = set(self.nodes.keys())
        converted = {
            nid for nid, node in self.nodes.items()
            if node.status == NodeStatus.CONVERTED
        }
        return [
            node for node in self.nodes.values()
            if node.status == NodeStatus.NOT_STARTED
            and all(
                dep in converted
                for dep in node.type_dependencies
                if dep in manifest_ids
            )
            and all(
                dep in converted
                for dep in node.call_dependencies
                if dep in manifest_ids
            )
        ]

    def auto_convert_structural_nodes(self, path: Path) -> int:
        """Mark all structural nodes (no function body to translate) as CONVERTED.

        CLASS, INTERFACE, ENUM, and TYPE_ALIAS nodes are fully represented by the
        skeleton — they require no agent invocation. Returns the count converted.
        """
        count = 0
        for node_id, node in self.nodes.items():
            if node.node_kind in _STRUCTURAL_KINDS and node.status == NodeStatus.NOT_STARTED:
                self.nodes[node_id] = node.model_copy(
                    update={"status": NodeStatus.CONVERTED}
                )
                count += 1
        if count:
            self.save(path)
        return count

    def update_node(self, path: Path, node_id: str, **fields: object) -> None:
        """Update a node's fields and persist the manifest to disk."""
        self.nodes[node_id] = self.nodes[node_id].model_copy(update=fields)
        self.save(path)

    def compute_topology(self) -> None:
        """Kahn's algorithm over the unified dependency graph.

        Sets topological_order and bfs_level on every node.
        Raises ValueError if a cycle is detected.
        Nodes whose dependencies point outside the manifest are treated as leaves.
        """
        from collections import deque

        def deps(node: ConversionNode) -> list[str]:
            seen: set[str] = set()
            result: list[str] = []
            for d in node.type_dependencies + node.call_dependencies:
                if d in self.nodes and d not in seen:
                    seen.add(d)
                    result.append(d)
            return result

        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        dependents: dict[str, list[str]] = {nid: [] for nid in self.nodes}

        for nid, node in self.nodes.items():
            for dep in deps(node):
                in_degree[nid] += 1
                dependents[dep].append(nid)

        bfs_levels: dict[str, int] = {}
        queue: deque[str] = deque()
        for nid, deg in in_degree.items():
            if deg == 0:
                queue.append(nid)
                bfs_levels[nid] = 0

        order = 0
        while queue:
            nid = queue.popleft()
            node = self.nodes[nid]
            self.nodes[nid] = node.model_copy(update={
                "topological_order": order,
                "bfs_level": bfs_levels[nid],
            })
            order += 1
            for dependent in dependents[nid]:
                in_degree[dependent] -= 1
                bfs_levels[dependent] = max(
                    bfs_levels.get(dependent, 0),
                    bfs_levels[nid] + 1,
                )
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if order != len(self.nodes):
            remaining = [nid for nid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Dependency cycle detected involving: {remaining}")
