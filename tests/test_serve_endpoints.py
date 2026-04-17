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
