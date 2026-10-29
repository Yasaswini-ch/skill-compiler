// Pure logic for the panel (no DOM), so it can be tested with Node: node --test extension/tests/panel-core.test.js
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.PanelCore = factory();
})(typeof self !== "undefined" ? self : this, function () {
  const initialState = () => ({ steps: [], finalOutput: null, error: null, done: false, mock: false });

  /* Split streamed text into complete lines; the unfinished last piece is returned to be joined with the next chunk. */
  function takeLines(buffer, chunk) {
    const parts = (buffer + chunk).split("\n");
    const rest = parts.pop();
    return { lines: parts.filter(l => l.trim()), rest };
  }

  function parseLine(line) {
    try { const e = JSON.parse(line); return e && typeof e === "object" && typeof e.type === "string" ? e : null; } catch (_) { return null; }
  }

  /* One event in, a new state out. A step shows running until its step_end, then pass, repaired or fail. */
  function applyEvent(state, e) {
    const s = { ...state, steps: state.steps.map(x => ({ ...x })) };
    const find = id => s.steps.find(x => x.id === id);
    switch (e.type) {
      case "plan":
        s.steps = (e.steps || []).map(p => ({ id: p.id, title: p.title, state: "pending", note: "", attempts: 0 }));
        break;
      case "step_start": {
        const st = find(e.step_id) || (s.steps.push({ id: e.step_id, title: e.title, state: "pending", note: "", attempts: 0 }), s.steps[s.steps.length - 1]);
        st.state = "running";
        break;
      }
      case "attempt_end": {
        const st = find(e.step_id);
        if (st) { st.attempts = e.attempt; if (!e.ok) st.note = e.checker_note || "rejected"; }   // the last rejection reason stays visible
        break;
      }
      case "step_end": {
        const st = find(e.step_id);
        if (st) st.state = e.status === "pass" || e.status === "repaired" ? e.status : "fail";
        break;
      }
      case "run_end":
        s.finalOutput = e.trace && typeof e.trace.final_output === "string" ? e.trace.final_output : "";
        s.mock = !!(e.trace && e.trace.mock === true);
        s.done = true;
        break;
      case "error":
        s.error = String(e.message || "The run failed.");
        s.done = true;
        break;
      default:
    }
    return s;
  }

  const LABELS = { pending: "waiting", running: "running", pass: "passed", repaired: "repaired", fail: "failed" };
  const label = state => LABELS[state] || state;

  return { initialState, takeLines, parseLine, applyEvent, label };
});
