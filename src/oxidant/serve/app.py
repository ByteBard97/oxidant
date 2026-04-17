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
    manifest_path: str
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
        config_path = Path(req.manifest_path).parent / "oxidant.config.json"
        cfg: dict[str, Any] = {}
        if config_path.exists():
            cfg = _json.loads(config_path.read_text())

        # review_mode from request overrides config
        cfg["review_mode"] = req.review_mode

        snippets = Path(req.snippets_dir)
        snippets.mkdir(parents=True, exist_ok=True)

        from oxidant.graph.state import OxidantState
        initial_state = OxidantState(
            manifest_path=str(Path(req.manifest_path).resolve()),
            target_path=str(Path(req.target_path).resolve()),
            snippets_dir=str(snippets.resolve()),
            config=cfg,
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
        manifest = cfg.get("manifest_path", "conversion_manifest.json")
        target = cfg.get("target_repo", "")
        return JSONResponse({
            "manifest_path": str((cfg_dir / manifest).resolve()),
            "target_path": str((cfg_dir / target).resolve()) if target else "",
            "snippets_dir": str((cfg_dir / cfg.get("snippets_dir", "snippets")).resolve()),
        })

    @app.get("/review-queue")
    async def get_review_queue() -> JSONResponse:
        """Return nodes that have been queued for human review across all runs."""
        return JSONResponse(_review_queue)

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
