"""
A tiny in-memory pub/sub so pipeline nodes can announce what they're doing
right now, and something else (the dashboard server) can listen in real time.

This is deliberately not tied to LangSmith or any external service - it's
just the pipeline narrating its own real progress as it runs, so a UI can
show it live. Nothing here is scripted or faked: every event corresponds to
something the pipeline actually just did.

If nothing is subscribed (e.g. you're running run.py from the CLI, not the
dashboard), emit() is a cheap no-op - existing behavior is untouched.
"""

import queue
import threading
import time

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()


def subscribe() -> queue.Queue:
    """Called by a listener (the dashboard's SSE endpoint) to start
    receiving events. Returns a Queue to read from."""
    q: queue.Queue = queue.Queue()
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def emit(event_type: str, **data) -> None:
    """Called by pipeline nodes to announce something happened. Safe to
    call even with zero subscribers (CLI runs)."""
    with _lock:
        subs = list(_subscribers)
    if not subs:
        return
    event = {"type": event_type, "ts": time.time(), **data}
    for q in subs:
        q.put(event)


def clear_subscribers() -> None:
    """Used when starting a fresh run from the dashboard, so a leftover
    listener from a previous run doesn't get confused."""
    with _lock:
        _subscribers.clear()
