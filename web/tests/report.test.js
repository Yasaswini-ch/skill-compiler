// Run with: node --test web/tests/report.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const R = require("../report.js");

const trace = {
  run_id: "r-1", skill: "demo <b>skill</b>", mode: "harness", model: "m", mock: false, input: "Hi <script>alert(1)</script>",
  final_output: '{"a": "<img src=x onerror=1>"}', totals: { llm_calls: 6, latency_ms: 3900, retries: 1, cache_hits: 0 },
  steps: [
    { step_id: 1, title: "Name", status: "pass", attempts: [{ output: "Ravi", format_ok: true, verified: true, checker_note: "ok", latency_ms: 640 }] },
    { step_id: 2, title: "Class", status: "repaired", attempts: [
      { output: "It looks like billing", format_ok: false, verified: false, checker_note: "Expected one word <now>", latency_ms: 710 },
      { output: "billing", format_ok: true, verified: true, checker_note: "ok", latency_ms: 520, model: "big" }] },
    { step_id: 3, title: "Bad", status: "fail", attempts: [{ output: "", format_ok: false, verified: false, checker_note: "Output is empty", latency_ms: 10 }] },
  ],
};

test("every step and every attempt is in the report with its verdicts", () => {
  const html = R.buildReportHtml(trace, { generatedAt: "2026-10-28T00:00:00Z" });
  for (const needle of ["Step 1: Name", "Step 2: Class", "Step 3: Bad", "attempt 1 · accepted", "attempt 1 · rejected", "attempt 2 · accepted",
    "format check: not ok", "model verifier: no", "passed first try", "repaired after a retry", "failed", "on big", "Output is empty", "6 model calls", "3.9 s"]) {
    assert.ok(html.includes(needle), "missing: " + needle);
  }
  assert.ok(html.includes("<b>1</b> steps passed first try, <b>1</b> repaired, <b>1</b> failed"));
});

test("everything from the trace is escaped", () => {
  const html = R.buildReportHtml(trace);
  assert.ok(!html.includes("<script>alert(1)</script>") && !html.includes("<img src=x") && !html.includes("<b>skill</b>"));
  assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;") && html.includes("Expected one word &lt;now&gt;"));
  assert.strictEqual(R.esc(null), "");
  assert.strictEqual(R.esc(`a&b"c'd`), "a&amp;b&quot;c&#39;d");
});

test("the file is self-contained: no scripts, links, images or web addresses", () => {
  const html = R.buildReportHtml(trace);
  assert.ok(!/<script/i.test(html) && !/<link/i.test(html) && !/<img/i.test(html) && !/<iframe/i.test(html));
  assert.ok(!/https?:\/\//i.test(html) && !/\s(src|href)\s*=\s*["']/i.test(html));   // no attribute can load or link anything
  assert.ok(/<style>/.test(html) && /^<!doctype html>/i.test(html));
});

test("a mock trace says MOCK, a real one does not", () => {
  assert.ok(R.buildReportHtml({ ...trace, mock: true }).includes("MOCK TRACE"));
  assert.ok(!R.buildReportHtml(trace).includes("MOCK TRACE"));
});

test("a run with no steps and a thin trace still produce a report", () => {
  const plain = R.buildReportHtml({ skill: "p", mode: "plain", steps: [], totals: { llm_calls: 1 }, final_output: "hi" });
  assert.ok(plain.includes("no steps") && plain.includes("hi"));
  assert.ok(R.buildReportHtml({}).includes("Run report"));
});

test("file names are safe", () => {
  assert.strictEqual(R.fileName({ run_id: "r-1" }), "report-r-1.html");
  const hostile = R.fileName({ skill: "../../etc/passwd" });
  assert.ok(!/[\/]/.test(hostile) && hostile.startsWith("report-") && hostile.endsWith(".html"), hostile);   // no path separators
  assert.strictEqual(R.fileName(null), "report-run.html");
});

test("the sample traces in the repo all build a report", () => {
  const dir = path.join(__dirname, "..", "..", "skillcompiler", "examples", "traces");
  const files = fs.readdirSync(dir).filter(f => f.endsWith(".json"));
  assert.ok(files.length >= 3);
  for (const f of files) {
    const t = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
    const html = R.buildReportHtml(t);
    assert.ok(html.includes(`Step ${t.steps[0].step_id}:`) && !/https?:\/\//i.test(html), f);
    assert.strictEqual((html.match(/class="attempt"/g) || []).length, t.steps.reduce((n, s) => n + s.attempts.length, 0), f);
  }
});
