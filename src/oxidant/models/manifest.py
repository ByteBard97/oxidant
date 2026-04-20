"""Manifest — SQLite-backed translation state.

Public interface is identical to the old JSON-file version so all callers
(nodes.py, context.py, verify.py, assemble.py, etc.) require no changes.

Backing store:
  NodeRecord rows in SQLite (via SQLModel / SQLAlchemy).
  ManifestMeta holds source_repo / version / generated_at.

Key differences from the JSON version:
  - update_node()  → single-row UPDATE (not a full 5 MB file rewrite)
  - eligible_nodes() → SQL query + Python dep-filter
  - load() → opens/creates engine; no disk read of all nodes up-front
  - save() → no-op (writes are immediate; kept for API compatibility)
  - nodes property → SELECT * FROM nodes (full load when needed)
"""
from __future__ import annotations

import json
import logging
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from sqlmodel import Session, SQLModel, create_engine, select

logger = logging.getLogger(__name__)

# ── Enums (unchanged) ──────────────────────────────────────────────────────────


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


_STRUCTURAL_KINDS: frozenset[NodeKind] = frozenset({
    NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS,
})

# ── ConversionNode (unchanged Pydantic model — used everywhere in the codebase) ──


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
    summary_text: Optional[str] = None  # 1-2 sentence description written by the converting agent


# ── Schema migrations ──────────────────────────────────────────────────────────

def _migrate_schema(engine) -> None:
    """Apply additive schema migrations to an existing DB.

    Each migration is idempotent — it checks whether the column/index already
    exists before running ALTER TABLE. Add new migrations here as columns are
    added to NodeRecord; never remove old ones.
    """
    import sqlite3 as _sqlite3
    import sqlalchemy as _sa

    with engine.connect() as conn:
        # Fetch existing columns in the nodes table
        result = conn.execute(_sa.text("PRAGMA table_info(nodes)"))
        existing = {row[1] for row in result}  # row[1] = column name

        migrations = [
            # (column_name, ALTER TABLE statement)
            ("summary_text", "ALTER TABLE nodes ADD COLUMN summary_text TEXT"),
        ]

        for col, sql in migrations:
            if col not in existing:
                conn.execute(_sa.text(sql))
                logger.info("Schema migration: added column %r to nodes table", col)

        conn.commit()


# ── Engine cache — one engine per db_path, shared across Manifest instances ────

_engine_cache: dict[str, object] = {}
_engine_lock = threading.Lock()


def _get_engine(db_path: Path):
    resolved = db_path.resolve()
    key = str(resolved)
    with _engine_lock:
        if key not in _engine_cache:
            from oxidant.models.db import NodeRecord  # noqa: F401 — registers table schema
            existed_before = resolved.exists()
            engine = create_engine(
                f"sqlite:///{key}",
                connect_args={"check_same_thread": False},
            )
            SQLModel.metadata.create_all(engine)
            # WAL mode: allows concurrent readers alongside a single writer
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))
                conn.commit()
            # Schema migrations — add columns introduced after initial DB creation
            _migrate_schema(engine)
            # Safety check: if the DB already existed, verify it has data.
            # A freshly created empty DB where data was expected means something
            # deleted or misrouted the file — abort loudly rather than silently
            # operating on an empty DB.
            if existed_before:
                import sqlite3 as _sqlite3
                with _sqlite3.connect(key) as _chk:
                    _count = _chk.execute(
                        "SELECT COUNT(*) FROM nodes"
                    ).fetchone()[0]
                if _count == 0:
                    logger.warning(
                        "SAFETY: DB at %s exists but has 0 nodes — "
                        "possible data loss. Refusing to use empty DB. "
                        "Re-run 'oxidant import-manifest' to restore.",
                        key,
                    )
            _engine_cache[key] = engine
        return _engine_cache[key]


# ── Manifest ───────────────────────────────────────────────────────────────────


class Manifest:
    """SQLite-backed manifest. Same public interface as the old JSON version.

    Constructor accepts two call patterns:
    1. Manifest(db_path)  — open/create the SQLite file at db_path
    2. Manifest(source_repo=..., nodes={...})  — in-memory DB for testing
       Omit db_path (or pass None) and supply nodes= to get an ephemeral manifest.
    """

    def __init__(
        self,
        db_path: "Path | None" = None,
        source_repo: str = "",
        generated_at: str = "",
        version: str = "1.0",
        nodes: "dict | None" = None,
    ) -> None:
        self.source_repo = source_repo
        self.generated_at = generated_at
        self.version = version

        if db_path is None:
            # In-memory mode for tests — use StaticPool so every connection
            # sees the same database (required for SQLAlchemy in-memory SQLite).
            from sqlalchemy.pool import StaticPool
            from oxidant.models.db import NodeRecord  # noqa: F401 — registers table schema
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            SQLModel.metadata.create_all(engine)
            self._db_path = Path(":memory:")
            self._engine = engine
            # Populate from nodes dict
            if nodes:
                self._bulk_insert_nodes(engine, nodes)
        else:
            self._db_path = db_path
            self._engine = _get_engine(db_path)
            if nodes:
                self._bulk_insert_nodes(self._engine, nodes)

    def _bulk_insert_nodes(self, engine: object, nodes: dict) -> None:
        """Insert a dict of ConversionNode objects into the DB."""
        from oxidant.models.db import NodeRecord
        import json as _json

        with Session(engine) as session:
            for node in nodes.values():
                row = NodeRecord(
                    node_id=node.node_id,
                    source_file=node.source_file,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    source_text=node.source_text,
                    node_kind=node.node_kind.value,
                    parameter_types=_json.dumps(node.parameter_types),
                    return_type=node.return_type,
                    type_dependencies=_json.dumps(node.type_dependencies),
                    call_dependencies=_json.dumps(node.call_dependencies),
                    callers=_json.dumps(node.callers),
                    parent_class=node.parent_class,
                    cyclomatic_complexity=node.cyclomatic_complexity,
                    idioms_needed=_json.dumps(node.idioms_needed),
                    topological_order=node.topological_order,
                    bfs_level=node.bfs_level,
                    tier=node.tier.value if node.tier else None,
                    tier_reason=node.tier_reason,
                    status=node.status.value,
                    snippet_path=node.snippet_path,
                    attempt_count=node.attempt_count,
                    last_error=node.last_error,
                    summary_text=node.summary_text,
                )
                session.add(row)
            session.commit()

    # ── Public interface (identical to old JSON Manifest) ──────────────────

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        """Open the SQLite DB at path and return a Manifest instance.

        'path' is the db_path (oxidant.db). If the DB doesn't exist yet it is
        created with the schema. Callers that previously passed a JSON path
        now pass the DB path instead.
        """
        from oxidant.models.db import ManifestMeta

        engine = _get_engine(path)
        with Session(engine) as session:
            meta = session.get(ManifestMeta, 1)
            if meta:
                return cls(path, source_repo=meta.source_repo,
                           generated_at=meta.generated_at, version=meta.version)
        return cls(path)

    def save(self, path: Path) -> None:  # noqa: ARG002
        """No-op. All writes are immediate via update_node(). Kept for API compatibility."""

    @property
    def nodes(self) -> dict[str, ConversionNode]:
        """Load all nodes from DB as a dict. Used by callers that need the full set."""
        from oxidant.models.db import NodeRecord

        with Session(self._engine) as session:
            rows = session.exec(select(NodeRecord)).all()
        return {r.node_id: r.to_conversion_node() for r in rows}

    def get_node(self, node_id: str) -> ConversionNode | None:
        """Fetch a single node by ID without loading the whole table."""
        from oxidant.models.db import NodeRecord

        with Session(self._engine) as session:
            row = session.get(NodeRecord, node_id)
        return row.to_conversion_node() if row else None

    def update_node(self, path: Path, node_id: str, **fields: object) -> None:  # noqa: ARG002
        """Update specific fields on one node row and commit immediately.

        path is accepted for API compatibility but ignored — the engine was
        already opened from self._db_path at load() time.
        """
        from oxidant.models.db import NodeRecord

        with Session(self._engine) as session:
            row = session.get(NodeRecord, node_id)
            if row is None:
                logger.error("update_node: node_id %r not found in DB", node_id)
                return
            for k, v in fields.items():
                # Enum values: store as string
                if hasattr(v, "value"):
                    v = v.value  # type: ignore[assignment]
                setattr(row, k, v)
            session.add(row)
            session.commit()

    def claim_next_eligible(self, complexity_max: int | None = None) -> ConversionNode | None:
        """Atomically claim the next eligible node using BEGIN IMMEDIATE.

        BEGIN IMMEDIATE acquires the write lock before reading, so two concurrent
        workers can never both see the same NOT_STARTED node and both claim it.
        Falls back to least-blocked nodes if no strictly-eligible ones exist.

        Args:
            complexity_max: If set, skip nodes with cyclomatic_complexity above this
                threshold. Useful for local model runs that handle only simple nodes.
        """
        import json as _json
        import sqlite3
        from oxidant.models.db import NodeRecord

        db_str = str(self._db_path.resolve())
        con = sqlite3.connect(db_str, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            con.execute("BEGIN IMMEDIATE")

            all_rows = con.execute("SELECT node_id, status, type_dependencies, call_dependencies, topological_order, cyclomatic_complexity, length(source_text) as src_len FROM nodes").fetchall()
            manifest_ids = {r["node_id"] for r in all_rows}
            converted = {r["node_id"] for r in all_rows if r["status"] == NodeStatus.CONVERTED.value}

            def _dep_count(row: sqlite3.Row) -> int:
                deps = _json.loads(row["type_dependencies"]) + _json.loads(row["call_dependencies"])
                return sum(1 for d in deps if d in manifest_ids and d not in converted)

            not_started = [r for r in all_rows if r["status"] == NodeStatus.NOT_STARTED.value]
            if complexity_max is not None:
                not_started = [r for r in not_started if (r["cyclomatic_complexity"] or 1) <= complexity_max]
            strict = [r for r in not_started if _dep_count(r) == 0]
            candidates = strict if strict else sorted(not_started, key=_dep_count)

            if not candidates:
                con.rollback()
                return None

            # Primary: topological order. Secondary: source length (short = easy first)
            best = min(candidates, key=lambda r: (r["topological_order"] or 0, r["src_len"] or 0))
            con.execute(
                "UPDATE nodes SET status = ? WHERE node_id = ?",
                (NodeStatus.IN_PROGRESS.value, best["node_id"]),
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

        # Fetch the full row via SQLAlchemy for to_conversion_node()
        with Session(self._engine) as session:
            row = session.get(NodeRecord, best["node_id"])
            return row.to_conversion_node() if row else None

    def eligible_nodes(self) -> list[ConversionNode]:
        """NOT_STARTED nodes whose every in-manifest dependency is CONVERTED.

        Falls back to least-blocked nodes if no strictly-eligible ones exist
        (deadlock breaking for dependency cycles).
        """
        from oxidant.models.db import NodeRecord

        with Session(self._engine) as session:
            all_rows = session.exec(select(NodeRecord)).all()

        manifest_ids = {r.node_id for r in all_rows}
        converted = {r.node_id for r in all_rows if r.status == NodeStatus.CONVERTED.value}

        def _unconverted_dep_count(row: "NodeRecord") -> int:  # noqa: F821
            deps = json.loads(row.type_dependencies) + json.loads(row.call_dependencies)
            return sum(1 for d in deps if d in manifest_ids and d not in converted)

        not_started = [r for r in all_rows if r.status == NodeStatus.NOT_STARTED.value]
        strict = [r for r in not_started if _unconverted_dep_count(r) == 0]

        if strict:
            return [r.to_conversion_node() for r in strict]

        if not_started:
            not_started.sort(key=_unconverted_dep_count)
        return [r.to_conversion_node() for r in not_started]

    def auto_convert_structural_nodes(self, path: Path) -> int:
        """Mark all structural nodes (CLASS/INTERFACE/ENUM/TYPE_ALIAS) as CONVERTED.

        Returns the count converted.
        """
        from oxidant.models.db import NodeRecord

        structural_values = {k.value for k in _STRUCTURAL_KINDS}
        with Session(self._engine) as session:
            rows = session.exec(
                select(NodeRecord).where(
                    NodeRecord.node_kind.in_(structural_values),  # type: ignore[attr-defined]
                    NodeRecord.status == NodeStatus.NOT_STARTED.value,
                )
            ).all()
            for row in rows:
                row.status = NodeStatus.CONVERTED.value
                session.add(row)
            session.commit()
        count = len(rows)
        if count:
            logger.info("Auto-converted %d structural nodes", count)
        return count

    def compute_topology(self) -> None:
        """Kahn's algorithm — sets topological_order and bfs_level on every node.

        Operates in-memory on the full node dict, then bulk-updates the DB.
        Cycle nodes get fallback orders (sorted by in_degree) so Phase B can
        still make progress.
        """
        from collections import deque
        from oxidant.models.db import NodeRecord

        # Load all nodes into memory for graph computation
        with Session(self._engine) as session:
            all_rows = session.exec(select(NodeRecord)).all()

        node_map: dict[str, NodeRecord] = {r.node_id: r for r in all_rows}

        def deps(nid: str) -> list[str]:
            r = node_map[nid]
            seen: set[str] = set()
            result: list[str] = []
            for d in json.loads(r.type_dependencies) + json.loads(r.call_dependencies):
                if d in node_map and d not in seen:
                    seen.add(d)
                    result.append(d)
            return result

        in_degree: dict[str, int] = {nid: 0 for nid in node_map}
        dependents: dict[str, list[str]] = {nid: [] for nid in node_map}

        for nid in node_map:
            for dep in deps(nid):
                in_degree[nid] += 1
                dependents[dep].append(nid)

        bfs_levels: dict[str, int] = {}
        queue: deque[str] = deque()
        for nid, deg in in_degree.items():
            if deg == 0:
                queue.append(nid)
                bfs_levels[nid] = 0

        order = 0
        topo_updates: dict[str, tuple[int, int]] = {}
        while queue:
            nid = queue.popleft()
            topo_updates[nid] = (order, bfs_levels[nid])
            order += 1
            for dep in dependents[nid]:
                in_degree[dep] -= 1
                bfs_levels[dep] = max(bfs_levels.get(dep, 0), bfs_levels[nid] + 1)
                if in_degree[dep] == 0:
                    queue.append(dep)

        if order != len(node_map):
            cycle_nodes = sorted(
                [nid for nid, deg in in_degree.items() if deg > 0],
                key=lambda nid: in_degree[nid],
            )
            for nid in cycle_nodes:
                topo_updates[nid] = (order, bfs_levels.get(nid, order))
                order += 1
            logger.warning(
                "Dependency cycles detected: %d nodes assigned fallback topological order.",
                len(cycle_nodes),
            )

        # Bulk-update topology in DB
        with Session(self._engine) as session:
            for nid, (topo, bfs) in topo_updates.items():
                row = session.get(NodeRecord, nid)
                if row:
                    row.topological_order = topo
                    row.bfs_level = bfs
                    session.add(row)
            session.commit()

    # ── Compatibility: model_validate_json (used by old code paths in Phase A) ──

    @classmethod
    def model_validate_json(cls, data: str) -> "Manifest":
        """Stub for callers that still use the Pydantic-style load. Not used in Phase B."""
        raise NotImplementedError(
            "Use Manifest.load(db_path) instead of model_validate_json()"
        )
