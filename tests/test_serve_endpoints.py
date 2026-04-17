def test_fastapi_importable():
    import fastapi  # noqa: F401
    import sse_starlette  # noqa: F401
    from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
