"""Manages active Phase B translation runs for the FastAPI serve command.

Each run is identified by a thread_id (str). The RunManager:
- Starts graph.astream() as an asyncio Task
- Feeds LangGraph node-update events into a per-run asyncio.Queue
- Tracks run status
- Handles pause (task cancellation; SqliteSaver persists last node) and abort

Pause vs resume:
  Pause:  POST /pause → cancel the asyncio Task. The SqliteSaver has already
          checkpointed after the last completed node. Resume by calling
          start_run() again with the same thread_id and initial_state — the
          graph will resume from the checkpoint.
  Abort:  POST /abort → cancel the asyncio Task + mark status "aborted".
          No resume.
  Interrupt (interactive review):
          supervisor_node calls LangGraph interrupt(). The Task is suspended
          inside graph.astream() waiting for a Command(resume=...).
          POST /resume sends the Command via graph.astream() continuation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

RunStatus = Literal["running", "paused", "interrupted", "complete", "aborted", "error"]


@dataclass
class RunState:
    thread_id: str
    status: RunStatus
    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None
    final_state: dict | None = None
    error: str | None = None


class RunManager:
    """Manages active Phase B runs."""

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: Path for the SqliteSaver checkpoint DB, or ":memory:" for tests.
        """
        self._db_path = db_path
        self._runs: dict[str, RunState] = {}
        self._graph = None  # lazy-initialised on first run

    def _get_graph(self):
        if self._graph is None:
            from oxidant.graph.graph import build_checkpointed_graph
            self._graph = build_checkpointed_graph(self._db_path)
        return self._graph

    def get_status(self, thread_id: str) -> RunStatus | None:
        run = self._runs.get(thread_id)
        return run.status if run else None

    async def start_run(
        self,
        thread_id: str,
        initial_state: dict[str, Any],
    ) -> None:
        """Start or resume a run. If a checkpoint exists for thread_id, the graph
        resumes from the last checkpoint (initial_state is used only for fresh runs).
        Parallel workers are spun up when config["parallelism"] > 1.
        """
        if thread_id in self._runs and self._runs[thread_id].status == "running":
            raise ValueError(f"Run {thread_id} is already running")

        run = RunState(thread_id=thread_id, status="running")
        self._runs[thread_id] = run

        parallelism = initial_state.get("config", {}).get("parallelism", 1)
        graph = self._get_graph()

        async def _stream_worker(worker_id: int, worker_state: dict[str, Any]) -> None:
            """Stream one worker's graph to the shared event queue."""
            from oxidant.serve.events import event_from_node_update
            config = {"configurable": {"thread_id": f"{thread_id}_w{worker_id}"}}
            async for chunk in graph.astream(worker_state, config=config, stream_mode="updates"):
                for node_name, update in chunk.items():
                    for json_str in event_from_node_update(node_name, update):
                        await run.event_queue.put(json_str)

        async def _stream():
            from oxidant.serve.events import RunCompleteEvent
            from pathlib import Path as _Path
            from oxidant.graph.nodes import setup_worker_clones
            try:
                target = _Path(initial_state["target_path"])
                if parallelism > 1:
                    logger.info("Starting %d parallel workers for run %s", parallelism, thread_id)
                    setup_worker_clones(target, parallelism)
                    worker_states = [{**initial_state, "worker_id": i} for i in range(parallelism)]
                    await asyncio.gather(*[_stream_worker(i, ws) for i, ws in enumerate(worker_states)])
                else:
                    config = {"configurable": {"thread_id": thread_id}}
                    async for chunk in graph.astream(initial_state, config=config, stream_mode="updates"):
                        for node_name, update in chunk.items():
                            from oxidant.serve.events import event_from_node_update
                            for json_str in event_from_node_update(node_name, update):
                                await run.event_queue.put(json_str)

                run.status = "complete"
                # Emit authoritative final counts from manifest
                try:
                    from oxidant.models.manifest import Manifest, NodeStatus
                    manifest = Manifest.load(_Path(initial_state["db_path"]))
                    converted = sum(1 for n in manifest.nodes.values() if n.status == NodeStatus.CONVERTED)
                    needs_review = sum(1 for n in manifest.nodes.values() if n.status == NodeStatus.HUMAN_REVIEW)
                    await run.event_queue.put(RunCompleteEvent(converted=converted, needs_review=needs_review).to_json())
                except Exception as exc:
                    logger.warning("Could not emit RunCompleteEvent: %s", exc)
                await run.event_queue.put(None)  # sentinel: stream done
            except asyncio.CancelledError:
                await run.event_queue.put(None)
                raise
            except Exception as exc:
                logger.exception("Run %s failed: %s", thread_id, exc)
                run.status = "error"
                run.error = str(exc)
                await run.event_queue.put(None)

        run.task = asyncio.create_task(_stream())

    async def pause(self, thread_id: str) -> None:
        """Cancel the running task. The SqliteSaver has checkpointed the last node.
        Resume by calling start_run() again with the same thread_id.
        """
        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")
        if run.task and not run.task.done():
            run.status = "paused"
            run.task.cancel()
            try:
                await run.task
            except asyncio.CancelledError:
                pass

    async def abort(self, thread_id: str) -> None:
        """Cancel the running task and mark as aborted (no resume)."""
        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")
        if run.task and not run.task.done():
            run.status = "aborted"
            run.task.cancel()
            try:
                await run.task
            except asyncio.CancelledError:
                pass

    async def resume_interrupt(
        self,
        thread_id: str,
        human_response: dict[str, Any],
    ) -> None:
        """Resume a graph that is paused at an interrupt() call.

        Sends a LangGraph Command(resume=human_response) to the graph.
        The graph resumes from the interrupt point and continues streaming.
        """
        from langgraph.types import Command

        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")

        graph = self._get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        # Re-start streaming with the Command — LangGraph resumes from the interrupt
        run.status = "running"

        async def _resume_stream():
            from oxidant.serve.events import event_from_node_update
            try:
                async for chunk in graph.astream(
                    Command(resume=human_response), config=config, stream_mode="updates"
                ):
                    for node_name, update in chunk.items():
                        for json_str in event_from_node_update(node_name, update):
                            await run.event_queue.put(json_str)
                run.status = "complete"
                await run.event_queue.put(None)
            except asyncio.CancelledError:
                await run.event_queue.put(None)
                raise
            except Exception as exc:
                logger.exception("Resumed run %s failed: %s", thread_id, exc)
                run.status = "error"
                run.error = str(exc)
                await run.event_queue.put(None)

        run.task = asyncio.create_task(_resume_stream())

    def get_event_queue(self, thread_id: str) -> asyncio.Queue:
        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")
        return run.event_queue
