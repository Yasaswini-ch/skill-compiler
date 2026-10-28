/* X-ray core: pure logic, no DOM. Runs in the browser (window.XRayCore) and in Node (module.exports), so it can be tested.
   It turns the harness's event stream (skillcompiler/stream.py) into a state object the renderer draws. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.XRayCore = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const attemptOk = a => !!(a.format_ok && a.verified);

  function initialState() {
    return { phase: "idle", mode: "full", route: null, skill: "", steps: [], attempts: 0, retries: 0,
             recordedMs: 0, calls: null, error: "", warnings: [], trace: null };
  }

  const mapStep = (state, id, fn) => ({ ...state, steps: state.steps.map(s => (s.id === id ? fn(s) : s)) });

  /* One event in, the next state out. Unknown events are ignored, so new optional events never break it. */
  function reduce(state, e) {
    switch (e && e.type) {
      case "run_start":
        return { ...initialState(), phase: e.will_split ? "splitting" : "running", mode: e.mode || "full" };
      case "route":
        return { ...state, route: { route: e.route, reason: e.reason || "" } };
      case "plan":
        return { ...state, phase: "running", skill: e.skill || "", warnings: e.warnings || [],
                 steps: (e.steps || []).map(s => ({ id: s.id, title: s.title, instruction: s.instruction || "",
                                                    state: "pending", kind: null, verified: null, attempts: [] })) };
      case "step_start":
        return mapStep(state, e.step_id, s => ({ ...s, state: "running" }));
      case "attempt_start":
        return mapStep(state, e.step_id, s => ({ ...s, attempts: [...s.attempts, {
          n: e.attempt, chip: "running", latencyMs: null, output: "", note: "", ok: false, model: e.model || "" }] }));
      case "attempt_end": {
        const next = mapStep(state, e.step_id, s => ({ ...s, attempts: s.attempts.map(a => (a.n === e.attempt
          ? { ...a, chip: e.ok ? "done" : "error", latencyMs: e.latency_ms || 0, output: e.output || "",
              note: e.checker_note || "", ok: !!e.ok, model: e.model || a.model }
          : a)) }));
        return { ...next, attempts: state.attempts + 1, retries: state.retries + (e.attempt > 1 ? 1 : 0),
                 recordedMs: state.recordedMs + (e.latency_ms || 0) };
      }
      case "step_end":
        return mapStep(state, e.step_id, s => ({ ...s, state: e.status === "fail" ? "failed" : "done", kind: e.status,
                                                  verified: e.verified == null ? null : !!e.verified }));
      case "run_end":
        return { ...state, phase: "done", trace: e.trace || null,
                 calls: e.trace && e.trace.totals ? e.trace.totals.llm_calls : null };
      case "error":
        return { ...state, phase: "error", error: e.message || "error" };
      default:
        return state;
    }
  }

  /* A recorded trace.json as the event sequence a live run would have produced. */
  function traceToEvents(trace) {
    const mode = (trace.mode_detail && trace.mode_detail.strategy) || "full";
    const events = [{ type: "run_start", will_split: true, mode }];
    if (trace.mode_detail && trace.mode_detail.route) {
      events.push({ type: "route", route: trace.mode_detail.route, reason: trace.mode_detail.reason || "" });
    }
    if (!trace.steps.length) {                       // a plain-route run has no steps
      events.push({ type: "run_end", trace });
      return events;
    }
    events.push({ type: "plan", skill: trace.skill, warnings: [],
                  steps: trace.steps.map(s => ({ id: s.step_id, title: s.title, instruction: s.instruction || "" })) });
    for (const s of trace.steps) {
      events.push({ type: "step_start", step_id: s.step_id, title: s.title });
      s.attempts.forEach((a, i) => {
        events.push({ type: "attempt_start", step_id: s.step_id, attempt: i + 1, ...(a.model ? { model: a.model } : {}) });
        events.push({ type: "attempt_end", step_id: s.step_id, attempt: i + 1, ok: attemptOk(a), ...a });
      });
      events.push({ type: "step_end", step_id: s.step_id, status: s.status });
    }
    events.push({ type: "run_end", trace });
    return events;
  }

  /* NDJSON events, a JSON array of events, or a whole trace.json: all give an event list. */
  function parseEvents(text) {
    const t = String(text).trim();
    if (!t) throw new Error("The file is empty.");
    if (t[0] === "[") return JSON.parse(t);
    try {
      const obj = JSON.parse(t);
      if (obj && Array.isArray(obj.steps)) return traceToEvents(obj);
      if (obj && obj.type) return [obj];
    } catch (_) { /* more than one line: NDJSON */ }
    return t.split(/\r?\n/).filter(l => l.trim()).map((l, i) => {
      try { return JSON.parse(l); } catch (e) { throw new Error(`Line ${i + 1} is not JSON: ${e.message}`); }
    });
  }

  /* Milliseconds to wait before showing an event in a replay. A recorded attempt of 3 s plays in about 1.2 s at speed 1. */
  function delayFor(e, speed) {
    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    let ms;
    switch (e.type) {
      case "attempt_end": ms = clamp((e.latency_ms || 0) * 0.4, 600, 2600); break;
      case "plan": ms = 900; break;
      case "step_end": ms = e.status === "fail" ? 700 : 350; break;
      case "run_end": ms = 600; break;
      default: ms = 250;
    }
    return ms / (speed || 1);
  }

  function summary(state) {
    const steps = state.steps;
    return { total: steps.length, passed: steps.filter(s => s.kind === "pass").length,
             repaired: steps.filter(s => s.kind === "repaired").length, failed: steps.filter(s => s.kind === "fail").length,
             activeId: (steps.find(s => s.state === "running") || {}).id || null };
  }

  return { attemptOk, initialState, reduce, traceToEvents, parseEvents, delayFor, summary };
});
