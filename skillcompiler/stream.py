"""Stream a run as newline-delimited JSON, one event per line, for live web pages.

    from flask import Response, stream_with_context
    from skillcompiler.stream import ndjson_events

    @app.post("/run-stream")
    def run_stream():
        body = request.get_json()
        events = ndjson_events(body["skill_text"], body["input"])
        return Response(stream_with_context(events), mimetype="application/x-ndjson")

The events are the ones run_skill reports (run_start, plan, step_start, attempt_start,
attempt_end, step_end, run_end) plus {"type": "error", "message": ...} if the run itself
raises. If the client disconnects, the generator is closed and the run stops at the next
event, so it does not keep spending API calls (a call already in flight finishes first).
"""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator

from . import runner


class StopRun(BaseException):
    """Raised inside the event callback to end a run early. Not an Exception on purpose,
    so the runner's guard around callbacks lets it through."""


def ndjson_events(skill_text: str, user_input: str, **kwargs) -> Iterator[str]:
    """Run the skill in a worker thread and yield each event as one JSON line."""
    events: queue.Queue = queue.Queue()
    cancelled = threading.Event()

    def on_event(event: dict) -> None:
        if cancelled.is_set():
            raise StopRun
        events.put(event)

    def work() -> None:
        try:
            runner.run_skill(skill_text, user_input, on_event=on_event, **kwargs)
        except StopRun:
            pass
        except Exception as exc:  # noqa: BLE001 - report it to the page instead of dying
            events.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()
    try:
        while True:
            event = events.get()
            if event is None:
                return
            yield json.dumps(event, ensure_ascii=False) + "\n"
    finally:
        cancelled.set()  # client went away (or we finished): stop at the next event
