import asyncio
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app_with_tmp(tmp_path):
    """Create a FastAPI app with temp paths (no real manifest needed for route tests)."""
    from oxidant.serve.app import create_app
    return create_app(
        db_path=str(tmp_path / "checkpoints.db"),
        gui_dist=None,  # no GUI in tests
    )


@pytest.mark.asyncio
async def test_status_404_for_unknown_thread(app_with_tmp):
    async with AsyncClient(transport=ASGITransport(app=app_with_tmp), base_url="http://test") as client:
        r = await client.get("/status/nonexistent-thread")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_review_queue_empty_initially(app_with_tmp):
    async with AsyncClient(transport=ASGITransport(app=app_with_tmp), base_url="http://test") as client:
        r = await client.get("/review-queue")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_resume_404_for_unknown_thread(app_with_tmp):
    async with AsyncClient(transport=ASGITransport(app=app_with_tmp), base_url="http://test") as client:
        r = await client.post("/resume/nonexistent", json={"hint": "try harder"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_manager_lifecycle():
    """RunManager creates a run, can be queried for status, and can be aborted."""
    from oxidant.serve.run_manager import RunManager

    rm = RunManager(db_path=":memory:")  # in-memory SQLite for tests
    assert rm.get_status("nonexistent") is None

    # We can't test a full graph run without real files, but we can test
    # that the RunManager initialises and rejects bad thread IDs cleanly.
    with pytest.raises(KeyError):
        await rm.abort("nonexistent")


def test_fastapi_importable():
    import fastapi  # noqa: F401
    import sse_starlette  # noqa: F401
    from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401


def test_sse_events_serialize_to_json():
    from oxidant.serve.events import NodeStartEvent, NodeCompleteEvent, RunCompleteEvent
    import json

    e = NodeStartEvent(node_id="foo/bar", tier="haiku")
    data = json.loads(e.to_json())
    assert data["event"] == "node_start"
    assert data["node_id"] == "foo/bar"
    assert data["tier"] == "haiku"

    e2 = NodeCompleteEvent(node_id="foo/bar", tier="sonnet", attempts=2)
    data2 = json.loads(e2.to_json())
    assert data2["event"] == "node_complete"
    assert data2["attempts"] == 2

    e3 = RunCompleteEvent(converted=10, needs_review=2)
    data3 = json.loads(e3.to_json())
    assert data3["event"] == "run_complete"
    assert data3["converted"] == 10
