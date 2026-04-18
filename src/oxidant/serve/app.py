"""FastAPI application for oxidant serve.

Endpoints:
  POST /run                   Start or resume a Phase B run
  GET  /stream/{thread_id}    SSE stream of progress events
  POST /pause/{thread_id}     Pause after current node (cancels task; resumable)
  POST /abort/{thread_id}     Abort run (cancels task; not resumable)
  POST /resume/{thread_id}    Resume a supervisor interrupt() pause
  GET  /review-queue          Nodes awaiting human review
  GET  /status/{thread_id}    Run status snapshot
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from oxidant.serve.run_manager import RunManager

logger = logging.getLogger(__name__)

_review_queue: list[dict] = []  # accumulated across all runs in this process


class StartRunRequest(BaseModel):
    db_path: str
    target_path: str
    snippets_dir: str = "snippets"
    review_mode: str = "auto"
    max_nodes: int | None = None
    thread_id: str | None = None  # None → generate new UUID


class ResumeRequest(BaseModel):
    hint: str = ""
    skip: bool = False


def create_app(db_path: str, gui_dist: str | None = None, config_path: str | None = None) -> FastAPI:
    """Factory that creates a configured FastAPI app.

    Args:
        db_path: Path to the SqliteSaver checkpoint DB file.
        gui_dist: Path to the built Vue 3 GUI dist/ directory, or None to skip.
    """
    app = FastAPI(title="Oxidant Serve", version="0.1.0")
    run_manager = RunManager(db_path=db_path)

    @app.post("/run")
    async def start_run(req: StartRunRequest) -> JSONResponse:
        """Start or resume a Phase B run. Returns the thread_id."""
        import json as _json

        thread_id = req.thread_id or str(uuid.uuid4())
        cfg: dict[str, Any] = {}
        if config_path:
            cfg_file = Path(config_path)
            if cfg_file.exists():
                cfg = _json.loads(cfg_file.read_text())

        # review_mode from request overrides config
        cfg["review_mode"] = req.review_mode

        snippets = Path(req.snippets_dir)
        snippets.mkdir(parents=True, exist_ok=True)

        from oxidant.graph.state import OxidantState
        initial_state = OxidantState(
            db_path=str(Path(req.db_path).resolve()),
            target_path=str(Path(req.target_path).resolve()),
            snippets_dir=str(snippets.resolve()),
            config=cfg,
            worker_id=0,
            current_node_id=None,
            current_prompt=None,
            current_snippet=None,
            current_tier=None,
            attempt_count=0,
            last_error=None,
            verify_status=None,
            review_queue=[],
            done=False,
            max_nodes=req.max_nodes,
            nodes_this_run=0,
            supervisor_hint=None,
            interrupt_payload=None,
            review_mode=req.review_mode,
        )

        await run_manager.start_run(thread_id=thread_id, initial_state=initial_state)
        return JSONResponse({"thread_id": thread_id, "status": "running"})

    @app.get("/stream/{thread_id}")
    async def stream_events(thread_id: str):
        """SSE stream of progress events for a run. Closes when the run completes."""
        if run_manager.get_status(thread_id) is None:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")

        queue = run_manager.get_event_queue(thread_id)

        async def event_generator():
            while True:
                item = await queue.get()
                if item is None:  # sentinel: stream is done
                    break
                yield {"data": item}

        return EventSourceResponse(event_generator())

    @app.post("/pause/{thread_id}")
    async def pause_run(thread_id: str) -> JSONResponse:
        """Pause a run after its current node. Resume by calling POST /run with the same thread_id."""
        try:
            await run_manager.pause(thread_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        return JSONResponse({"thread_id": thread_id, "status": "paused"})

    @app.post("/abort/{thread_id}")
    async def abort_run(thread_id: str) -> JSONResponse:
        """Abort a run. Not resumable."""
        try:
            await run_manager.abort(thread_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        return JSONResponse({"thread_id": thread_id, "status": "aborted"})

    @app.post("/resume/{thread_id}")
    async def resume_interrupt(thread_id: str, req: ResumeRequest) -> JSONResponse:
        """Resume a graph paused at a supervisor interrupt().

        Body: {"hint": "...", "skip": false}
        - hint: human-provided translation hint (overrides supervisor hint)
        - skip: if true, skip this node and queue for human review
        """
        if run_manager.get_status(thread_id) is None:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        try:
            await run_manager.resume_interrupt(
                thread_id=thread_id,
                human_response={"hint": req.hint, "skip": req.skip},
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return JSONResponse({"thread_id": thread_id, "status": "running"})

    @app.get("/api/defaults")
    async def get_defaults() -> JSONResponse:
        """Return default manifest/target paths from oxidant.config.json."""
        cfg_path = Path(config_path) if config_path else Path("oxidant.config.json")
        if not cfg_path.exists():
            return JSONResponse({})
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            return JSONResponse({})
        # Resolve paths relative to the config file's directory
        cfg_dir = cfg_path.parent
        target = cfg.get("target_repo", "")
        return JSONResponse({
            "db_path": str((cfg_dir / "oxidant.db").resolve()),
            "target_path": str((cfg_dir / target).resolve()) if target else "",
            "snippets_dir": str((cfg_dir / cfg.get("snippets_dir", "snippets")).resolve()),
        })

    @app.get("/review-queue")
    async def get_review_queue() -> JSONResponse:
        """Return nodes that have been queued for human review across all runs."""
        return JSONResponse(_review_queue)

    def _get_manifest_db() -> Path | None:
        """Resolve the manifest DB path from the config file."""
        cfg_path = Path(config_path) if config_path else Path("oxidant.config.json")
        if not cfg_path.exists():
            return None
        return (cfg_path.parent / "oxidant.db").resolve()

    @app.get("/api/stats")
    async def get_stats() -> JSONResponse:
        """Aggregate node counts by status."""
        db = _get_manifest_db()
        if db is None or not db.exists():
            return JSONResponse({"error": "oxidant.db not found"}, status_code=404)
        import sqlite3
        con = sqlite3.connect(str(db))
        rows = con.execute(
            "SELECT status, COUNT(*) FROM nodes GROUP BY status"
        ).fetchall()
        con.close()
        counts: dict[str, int] = {r[0]: r[1] for r in rows}
        total = sum(counts.values())
        return JSONResponse({
            "total": total,
            "converted": counts.get("converted", 0),
            "not_started": counts.get("not_started", 0),
            "in_progress": counts.get("in_progress", 0),
            "human_review": counts.get("human_review", 0),
            "failed": counts.get("failed", 0),
        })

    @app.get("/api/modules")
    async def get_modules() -> JSONResponse:
        """Per-module completion breakdown."""
        db = _get_manifest_db()
        if db is None or not db.exists():
            return JSONResponse({"error": "oxidant.db not found"}, status_code=404)
        import sqlite3
        con = sqlite3.connect(str(db))
        rows = con.execute(
            "SELECT source_file, status, COUNT(*) FROM nodes GROUP BY source_file, status"
        ).fetchall()
        con.close()

        # Aggregate per module
        modules: dict[str, dict[str, int]] = {}
        for source_file, status, count in rows:
            m = modules.setdefault(source_file, {
                "module": source_file, "total": 0,
                "converted": 0, "human_review": 0, "in_progress": 0, "not_started": 0,
            })
            m["total"] += count
            if status in m:
                m[status] += count

        result = []
        for m in sorted(modules.values(), key=lambda x: x["module"]):
            total = m["total"]
            pct = round(100 * m["converted"] / total) if total else 0
            result.append({**m, "pct_complete": pct})
        return JSONResponse(result)

    @app.get("/api/errors")
    async def get_errors() -> JSONResponse:
        """Top recurring error patterns across human_review nodes."""
        db = _get_manifest_db()
        if db is None or not db.exists():
            return JSONResponse({"error": "oxidant.db not found"}, status_code=404)
        import re
        import sqlite3
        con = sqlite3.connect(str(db))
        rows = con.execute(
            "SELECT node_id, last_error FROM nodes WHERE status = 'human_review' AND last_error IS NOT NULL"
        ).fetchall()
        con.close()

        # Strip node-specific parts to group similar errors
        _STRIP_RE = re.compile(
            r"\b(0x[0-9a-f]+|\d+\.\d+|\d+|`[^`]{1,60}`|\"[^\"]{1,60}\")\b",
            re.IGNORECASE,
        )

        pattern_map: dict[str, list[str]] = {}
        for node_id, error in rows:
            key = _STRIP_RE.sub("_", error or "").strip()[:200]
            pattern_map.setdefault(key, []).append(node_id)

        result = sorted(
            [{"pattern": p, "count": len(ids), "node_ids": ids[:10]}
             for p, ids in pattern_map.items()],
            key=lambda x: -x["count"],
        )
        return JSONResponse(result[:50])

    @app.get("/api/nodes")
    async def get_nodes(
        status: str | None = None,
        module: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        """Paginated node list with optional status and module filters."""
        db = _get_manifest_db()
        if db is None or not db.exists():
            return JSONResponse({"error": "oxidant.db not found"}, status_code=404)
        import sqlite3
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        where_parts = []
        params: list[object] = []
        if status:
            where_parts.append("status = ?")
            params.append(status)
        if module:
            where_parts.append("source_file LIKE ?")
            params.append(f"%{module}%")
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        count_row = con.execute(f"SELECT COUNT(*) FROM nodes {where}", params).fetchone()
        total = count_row[0] if count_row else 0
        rows = con.execute(
            f"SELECT node_id, source_file, node_kind, status, tier, attempt_count, last_error "
            f"FROM nodes {where} ORDER BY topological_order LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        con.close()
        return JSONResponse({
            "total": total,
            "limit": limit,
            "offset": offset,
            "nodes": [dict(r) for r in rows],
        })

    @app.get("/status/{thread_id}")
    async def get_status(thread_id: str) -> JSONResponse:
        status = run_manager.get_status(thread_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        return JSONResponse({"thread_id": thread_id, "status": status})

    # Serve built Vue GUI at / (must be mounted last so API routes take priority)
    if gui_dist and Path(gui_dist).exists():
        app.mount("/", StaticFiles(directory=gui_dist, html=True), name="gui")

    return app


# Module-level app instance for ``uvicorn oxidant.serve.app:app``
# Uses default paths; the serve CLI command calls create_app() directly.
app = create_app(db_path="oxidant_checkpoints.db")
