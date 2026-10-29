// Run with: node --test extension/tests/panel-core.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const P = require("../panel-core.js");

test("takeLines keeps the unfinished piece for the next chunk", () => {
  let r = P.takeLines("", '{"type":"a"}\n{"type":');
  assert.deepStrictEqual(r.lines, ['{"type":"a"}']);
  r = P.takeLines(r.rest, '"b"}\n');
  assert.deepStrictEqual(r.lines, ['{"type":"b"}']);
  assert.strictEqual(r.rest, "");
});

test("parseLine ignores junk and lines without a type", () => {
  assert.strictEqual(P.parseLine("not json"), null);
  assert.strictEqual(P.parseLine('{"a":1}'), null);
  assert.strictEqual(P.parseLine('[1]'), null);
  assert.strictEqual(P.parseLine('{"type":"plan"}').type, "plan");
});

test("a recorded run with one repair ends with pass, repaired, pass states and a final output", () => {
  const file = path.join(__dirname, "..", "..", "web", "mock", "events_repair.ndjson");
  let s = P.initialState();
  for (const line of fs.readFileSync(file, "utf8").split("\n").filter(Boolean)) s = P.applyEvent(s, P.parseLine(line));
  assert.strictEqual(s.done, true);
  assert.deepStrictEqual(s.steps.map(x => x.state), ["pass", "repaired", "pass", "pass", "pass", "pass"]);
  assert.match(s.steps[1].note, /Expected exactly one of/, "a repaired step keeps the reason its first try was rejected");
  assert.strictEqual(s.steps[0].note, "");
  assert.ok(s.finalOutput.length > 0);
});

test("a rejected attempt shows the checker's note while the step is still running", () => {
  let s = P.applyEvent(P.initialState(), { type: "plan", steps: [{ id: 1, title: "A" }] });
  s = P.applyEvent(s, { type: "step_start", step_id: 1, title: "A" });
  s = P.applyEvent(s, { type: "attempt_end", step_id: 1, attempt: 1, ok: false, checker_note: "needs JSON" });
  assert.strictEqual(s.steps[0].state, "running");
  assert.strictEqual(s.steps[0].note, "needs JSON");
  s = P.applyEvent(s, { type: "step_end", step_id: 1, status: "fail" });
  assert.strictEqual(s.steps[0].state, "fail");
  assert.strictEqual(s.steps[0].note, "needs JSON");
});

test("an error event ends the run and keeps the message; a mock trace is flagged", () => {
  const s = P.applyEvent(P.initialState(), { type: "error", message: "model down" });
  assert.deepStrictEqual([s.error, s.done], ["model down", true]);
  const m = P.applyEvent(P.initialState(), { type: "run_end", trace: { final_output: "x", mock: true } });
  assert.strictEqual(m.mock, true);
});

test("applyEvent does not change the state it was given", () => {
  const before = P.applyEvent(P.initialState(), { type: "plan", steps: [{ id: 1, title: "A" }] });
  const snapshot = JSON.stringify(before);
  P.applyEvent(before, { type: "step_start", step_id: 1, title: "A" });
  assert.strictEqual(JSON.stringify(before), snapshot);
});

test("the manifest asks for the permissions the plan allows and no others, and no key", () => {
  const m = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "manifest.json"), "utf8"));
  assert.strictEqual(m.manifest_version, 3);
  assert.deepStrictEqual([...m.permissions].sort(), ["activeTab", "contextMenus", "storage"]);
  assert.deepStrictEqual(m.host_permissions, ["http://127.0.0.1:5000/*"]);
  const all = fs.readdirSync(path.join(__dirname, "..")).filter(f => /\.(js|json|html)$/.test(f))
    .map(f => fs.readFileSync(path.join(__dirname, "..", f), "utf8")).join("\n");
  assert.ok(!/GEMINI_API_KEY|api[_-]?key\s*[:=]|AIza[0-9A-Za-z_-]{20}/i.test(all), "no API key anywhere in the extension");
});
