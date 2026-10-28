// Run with: node --test web/tests/xray-core.test.js
const test = require("node:test");
const assert = require("node:assert");
const X = require("../xray-core.js");

const trace = {
  skill: "demo", mock: false, totals: { llm_calls: 6, latency_ms: 3900, retries: 1 }, final_output: "{}",
  steps: [
    { step_id: 1, title: "Name", status: "pass", attempts: [{ output: "Ravi", format_ok: true, verified: true, checker_note: "ok", latency_ms: 640 }] },
    { step_id: 2, title: "Class", status: "repaired", attempts: [
      { output: "It looks like billing", format_ok: false, verified: false, checker_note: "Expected one word", latency_ms: 710 },
      { output: "billing", format_ok: true, verified: true, checker_note: "ok", latency_ms: 520 }] },
  ],
};
const run = events => events.reduce(X.reduce, X.initialState());

test("a trace becomes events in the live order and ends with the trace", () => {
  const ev = X.traceToEvents(trace);
  assert.deepStrictEqual(ev.map(e => e.type), ["run_start", "plan", "step_start", "attempt_start", "attempt_end", "step_end",
    "step_start", "attempt_start", "attempt_end", "attempt_start", "attempt_end", "step_end", "run_end"]);
  assert.strictEqual(ev[ev.length - 1].trace, trace);
  assert.strictEqual(ev.filter(e => e.type === "attempt_end")[1].ok, false);
});

test("replaying the events rebuilds the same step states", () => {
  const s = run(X.traceToEvents(trace));
  assert.strictEqual(s.phase, "done");
  assert.deepStrictEqual(s.steps.map(x => [x.state, x.kind]), [["done", "pass"], ["done", "repaired"]]);
  assert.strictEqual(s.steps[1].attempts.length, 2);
  assert.strictEqual(s.steps[1].attempts[0].chip, "error");
  assert.strictEqual(s.steps[1].attempts[1].chip, "done");
  assert.strictEqual(s.attempts, 3);
  assert.strictEqual(s.retries, 1);
  assert.strictEqual(s.recordedMs, 640 + 710 + 520);
  assert.strictEqual(s.calls, 6);
});

test("a step is running between its start and its end", () => {
  const ev = X.traceToEvents(trace);
  const s = run(ev.slice(0, 7));                    // up to step_start of step 2
  assert.strictEqual(s.steps[0].state, "done");
  assert.strictEqual(s.steps[1].state, "running");
  assert.strictEqual(X.summary(s).activeId, 2);
});

test("a failed step ends failed, an error event ends the run", () => {
  const failed = { ...trace, steps: [{ ...trace.steps[1], status: "fail" }] };
  assert.strictEqual(run(X.traceToEvents(failed)).steps[0].state, "failed");
  const s = run([{ type: "run_start", will_split: true }, { type: "error", message: "boom" }]);
  assert.strictEqual(s.phase, "error");
  assert.strictEqual(s.error, "boom");
});

test("unknown events are ignored and plan carries instructions", () => {
  const s0 = run([{ type: "run_start", will_split: false }, { type: "plan", skill: "x", steps: [{ id: 1, title: "T", instruction: "Do it" }] }]);
  assert.strictEqual(s0.steps[0].instruction, "Do it");
  assert.strictEqual(X.reduce(s0, { type: "from_the_future" }), s0);
});

test("a plain-route trace (no steps) goes straight to done", () => {
  const plain = { skill: "p", mode: "plain", steps: [], totals: { llm_calls: 1 }, final_output: "hi",
                  mode_detail: { strategy: "auto", route: "plain", reason: "lint score 5 (low), 3 steps" } };
  const s = run(X.traceToEvents(plain));
  assert.strictEqual(s.phase, "done");
  assert.strictEqual(s.route.route, "plain");
  assert.strictEqual(s.steps.length, 0);
});

test("parseEvents reads NDJSON, an array, and a whole trace", () => {
  const ev = X.traceToEvents(trace);
  const nd = ev.map(e => JSON.stringify(e)).join("\n") + "\n";
  assert.strictEqual(X.parseEvents(nd).length, ev.length);
  assert.strictEqual(X.parseEvents(JSON.stringify(ev)).length, ev.length);
  assert.strictEqual(X.parseEvents(JSON.stringify(trace)).length, ev.length);
  assert.throws(() => X.parseEvents(""), /empty/);
  assert.throws(() => X.parseEvents('{"type":"run_start"}\nnot json'), /Line 2/);
});

test("replay delays: attempts follow recorded latency within limits, speed divides", () => {
  assert.strictEqual(X.delayFor({ type: "attempt_end", latency_ms: 3000 }, 1), 1200);
  assert.strictEqual(X.delayFor({ type: "attempt_end", latency_ms: 10 }, 1), 600);
  assert.strictEqual(X.delayFor({ type: "attempt_end", latency_ms: 500000 }, 1), 2600);
  assert.strictEqual(X.delayFor({ type: "attempt_end", latency_ms: 3000 }, 2), 600);
  assert.ok(X.delayFor({ type: "step_end", status: "fail" }, 1) > X.delayFor({ type: "step_end", status: "pass" }, 1));
});
