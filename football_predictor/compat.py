"""Compatibility helpers for runtime quirks."""

# Py3.11 compatibility shim for libs that still use asyncio.coroutine
def patch_asyncio_for_py311() -> None:
    try:
        import asyncio
        import types

        if not hasattr(asyncio, "coroutine"):
            asyncio.coroutine = types.coroutine  # type: ignore[attr-defined]
    except Exception:
        # Best-effort; never crash app startup because of the shim
        pass
