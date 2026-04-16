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
        """NOT_STARTED nodes whose every dependency is CONVERTED."""
        converted = {
            nid for nid, node in self.nodes.items()
            if node.status == NodeStatus.CONVERTED
        }
        return [
            node for node in self.nodes.values()
            if node.status == NodeStatus.NOT_STARTED
            and all(dep in converted for dep in node.type_dependencies)
            and all(dep in converted for dep in node.call_dependencies)
        ]

    def update_node(self, path: Path, node_id: str, **fields: object) -> None:
        """Update a node's fields and persist the manifest to disk."""
        self.nodes[node_id] = self.nodes[node_id].model_copy(update=fields)
        self.save(path)
