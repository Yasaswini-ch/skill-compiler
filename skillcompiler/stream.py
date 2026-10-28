"""Stream a run as newline-delimited JSON, one event per line, for live web pages.

    from flask import Response, stream_with_context
    from skillcompiler.stream import ndjson_events

    @app.post("/run-stream")
    def run_stream():
        body = request.get_json()
        events = ndjson_events(body["skill_text"], body["input"], max_steps=6, timeout_s=120)
        return Response(stream_with_context(events), mimetype="application/x-ndjson")

The events are the ones run_skill reports (run_start, plan, step_start, attempt_start, attempt_end,
step_end, run_end). Every failure becomes exactly ONE {"type": "error", "message": ...} line, and then
the stream ends: the generator never raises into the web server. The failures covered:

* the plan has more steps than max_steps (the plan event is sent, then the error, before any step runs),
* the run takes longer than timeout_s (also when one model call hangs: the error is sent at the deadline),
* the model API fails 3 calls in a row (a missing key, no quota, an outage), so it stops spending calls,
* anything run_skill itself raises (a bad plan, an unknown mode).

If the client disconnects, the generator is closed and the run stops at the next event, so it does not
keep spending API calls (a call already in flight finishes first). Queued events are dropped.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Iterator

from . import runner

LLM_FAILURES_BEFORE_STOP = 3


class StopRun(BaseException):
    """Raised inside the event callback to end a run early. Not an Exception on purpose,
    so the runner's guard around callbacks lets it through."""


def _line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def ndjson_events(skill_text: str, user_input: str, *, verify: bool | None = None,
                  mode: str | None = None, max_steps: int | None = None,
                  timeout_s: float | None = None, **kwargs) -> Iterator[str]:
    """Run the skill in a worker thread and yield each event as one JSON line.

    verify and mode are passed to run_skill (None leaves its defaults). max_steps and timeout_s are
    limits, off when None. Other keyword arguments (model, plan, max_retries) go to run_skill too.
    """
    events: queue.Queue = queue.Queue()
    cancelled = threading.Event()
    state = {"error_sent": False, "llm_failures": 0}
    deadline = time.monotonic() + float(timeout_s) if timeout_s else None

    def fail(message: str) -> None:
        if not state["error_sent"]:  # exactly one error event per stream
            state["error_sent"] = True
            events.put({"type": "error", "message": message})

    def on_event(event: dict) -> None:
        if cancelled.is_set():
            raise StopRun
        events.put(event)
        kind = event.get("type")
        if kind == "plan":
            steps = event.get("steps") or []
            if not steps:
                fail("The skill produced no steps to run.")
                raise StopRun
            if max_steps and len(steps) > max_steps:
                fail(f"This skill splits into {len(steps)} steps; the limit here is {max_steps}.")
                raise StopRun
        elif kind == "attempt_end":
            note = str(event.get("checker_note", ""))
            if note.startswith("LLM call failed"):
                state["llm_failures"] += 1
                if state["llm_failures"] >= LLM_FAILURES_BEFORE_STOP:
                    fail(f"The model API failed {LLM_FAILURES_BEFORE_STOP} calls in a row, so the run was "
                         f"stopped: {note[len('LLM call failed: '):][:240]}")
                    raise StopRun
            else:
                state["llm_failures"] = 0

    def work() -> None:
        try:
            options = dict(kwargs)
            if verify is not None:
                options["verify"] = verify
            if mode is not None:
                options["mode"] = mode
            runner.run_skill(skill_text, user_input, on_event=on_event, **options)
        except StopRun:
            pass
        except Exception as exc:  # noqa: BLE001 - report it to the page instead of dying
            fail(f"{type(exc).__name__}: {exc}")
        finally:
            events.put(None)

    def timed_out_line() -> str:
        return _line({"type": "error", "message": f"The run took longer than {timeout_s} s and was stopped."})

    threading.Thread(target=work, daemon=True).start()
    try:
        while True:
            wait = None if deadline is None else max(0.0, deadline - time.monotonic())
            try:
                event = events.get(timeout=wait)
            except queue.Empty:  # nothing arrived before the deadline, e.g. one call is hanging
                if not state["error_sent"]:
                    yield timed_out_line()
                return
            if event is None:
                return
            if deadline is not None and time.monotonic() > deadline and event.get("type") != "error":
                if not state["error_sent"]:
                    state["error_sent"] = True
                    yield timed_out_line()
                return
            yield _line(event)
    except Exception as exc:  # noqa: BLE001 - the generator must never raise into the server
        if not state["error_sent"]:
            yield _line({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        cancelled.set()  # client went away (or we finished): stop at the next event
        while not events.empty():  # drop anything still queued
            try:
                events.get_nowait()
            except queue.Empty:
                break
