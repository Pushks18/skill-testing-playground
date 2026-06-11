# eval/tracing.py
"""Langfuse tracing for eval runs — strictly optional, never load-bearing.

Enabled only when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set; without
them every helper is a no-op so tests and CI run key-free. Host comes from
LANGFUSE_HOST or the legacy LANGFUSE_BASE_URL.

Usage (run_task):
    handler = langfuse_handler()                  # None when disabled
    config["callbacks"] = [handler] if handler else []
    ...
    url = langfuse_trace_url(handler)             # "" when unavailable
"""
from __future__ import annotations

import os


def langfuse_enabled() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def _host() -> str:
    return (
        os.environ.get("LANGFUSE_HOST")
        or os.environ.get("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    ).rstrip("/")


def langfuse_handler(**trace_metadata):
    """Return a LangChain CallbackHandler, or None when disabled/unavailable.

    Import is lazy and failure-tolerant: a broken or missing langfuse install
    must never take down an eval run.
    """
    if not langfuse_enabled():
        return None
    os.environ.setdefault("LANGFUSE_HOST", _host())
    try:
        from langfuse.langchain import CallbackHandler  # langfuse >= 3 (OTel)
    except ImportError:
        try:
            from langfuse.callback import CallbackHandler  # langfuse 2.x
        except ImportError:
            return None
    try:
        return CallbackHandler()
    except Exception:
        return None


def langfuse_trace_url(handler) -> str:
    """Best-effort public URL for the trace a handler just recorded.

    SDK majors expose the id differently; probe known attributes and fall back
    to empty string — callers treat "" as 'no trace link'.
    """
    if handler is None:
        return ""
    trace_id = (
        getattr(handler, "last_trace_id", None)
        or getattr(handler, "trace_id", None)
        or getattr(getattr(handler, "trace", None), "id", None)
    )
    if not trace_id:
        try:
            from langfuse import get_client
            trace_id = get_client().get_current_trace_id()
        except Exception:
            trace_id = None
    return f"{_host()}/trace/{trace_id}" if trace_id else ""


def langfuse_flush() -> None:
    """Flush buffered events (call once at the end of a batch, not per run)."""
    if not langfuse_enabled():
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception:
        pass
