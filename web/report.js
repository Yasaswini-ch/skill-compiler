/* Proof report: turn one trace.json into a single self-contained HTML file (inline CSS, no scripts, no external requests).
   It lists every step with its status and every attempt with its output, format result, verifier result and checker note.
   Pure function: works in the browser (window.ProofReport) and in Node (module.exports), so it is tested. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ProofReport = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const secs = ms => (ms == null ? "?" : (ms / 1000).toFixed(1) + " s");
  const WORD = { pass: "passed first try", repaired: "repaired after a retry", fail: "failed" };

  const CSS = `
:root{--bg:#fff;--ink:#14181f;--muted:#566072;--line:#d6dbe4;--pass:#14804a;--rep:#9a5b00;--fail:#b42318;--soft:#f4f6f9}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--ink:#e7eaf1;--muted:#9aa4b6;--line:#2c374c;--pass:#3ddc97;--rep:#f5b84a;--fail:#ff7b7b;--soft:#161b24}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:28px 18px 60px}h1{margin:.1em 0 .2em;font-size:1.7em}h2{margin:1.6em 0 .4em;font-size:1.15em}
.meta{color:var(--muted);font:14px ui-monospace,Consolas,monospace}.banner{margin:0 0 16px;padding:10px 14px;border:3px solid var(--fail);color:var(--fail);font-weight:800;border-radius:8px}
.step{border:2px solid var(--line);border-radius:10px;padding:12px 16px;margin:14px 0}.step[data-k=pass]{border-color:var(--pass)}.step[data-k=repaired]{border-color:var(--rep)}.step[data-k=fail]{border-color:var(--fail)}
.badge{float:right;font:700 13px ui-monospace,Consolas,monospace;text-transform:uppercase}.step[data-k=pass] .badge{color:var(--pass)}.step[data-k=repaired] .badge{color:var(--rep)}.step[data-k=fail] .badge{color:var(--fail)}
.attempt{border-left:5px solid var(--line);padding:4px 0 4px 12px;margin:10px 0}.attempt[data-ok=true]{border-color:var(--pass)}.attempt[data-ok=false]{border-color:var(--fail)}
.row{font:13px ui-monospace,Consolas,monospace;color:var(--muted)}pre{background:var(--soft);padding:10px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0;font:13px/1.45 ui-monospace,Consolas,monospace}
.note{color:var(--fail);font-weight:600}.foot{margin-top:2.4em;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:14px}`;

  function attemptHtml(a, i) {
    const ok = !!(a.format_ok && a.verified);
    return `<div class="attempt" data-ok="${ok}">
<div class="row">attempt ${i + 1} · ${ok ? "accepted" : "rejected"} · format check: ${a.format_ok ? "ok" : "not ok"} · model verifier: ${a.verified ? "yes" : "no"} · ${esc(secs(a.latency_ms))}${a.model ? " · on " + esc(a.model) : ""}</div>
<pre>${esc(a.output || "(no output)")}</pre>${!ok && a.checker_note ? `<div class="note">Checker: ${esc(a.checker_note)}</div>` : ""}</div>`;
  }

  function stepHtml(s) {
    const kind = s.status === "fail" ? "fail" : s.status === "repaired" ? "repaired" : "pass";
    return `<section class="step" data-k="${kind}"><span class="badge">${esc(WORD[kind])}</span><h2 style="margin-top:0">Step ${esc(s.step_id)}: ${esc(s.title)}</h2>${(s.attempts || []).map(attemptHtml).join("")}</section>`;
  }

  function buildReportHtml(trace, opts) {
    const t = trace || {}, totals = t.totals || {}, steps = t.steps || [];
    const counts = { pass: 0, repaired: 0, fail: 0 };
    for (const s of steps) counts[s.status === "fail" ? "fail" : s.status === "repaired" ? "repaired" : "pass"]++;
    const when = (opts && opts.generatedAt) || new Date().toISOString();
    const mock = t.mock === true;
    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Run report: ${esc(t.skill || "skill")}</title><style>${CSS}</style></head><body><main>
${mock ? '<div class="banner">MOCK TRACE: produced by a stand-in, not the real harness. Do not use it as a result.</div>' : ""}
<div class="meta">RUN REPORT</div><h1>${esc(t.skill || "skill")}</h1>
<p class="meta">${esc(t.model || "model unknown")} · ${esc(t.mode || "harness")} · ${esc(totals.llm_calls)} model calls · ${esc(secs(totals.latency_ms))} · ${esc(totals.retries)} retries${totals.cache_hits != null ? " · " + esc(totals.cache_hits) + " cache hits" : ""} · run ${esc(t.run_id || "?")}</p>
<p><b>${counts.pass}</b> steps passed first try, <b>${counts.repaired}</b> repaired, <b>${counts.fail}</b> failed.</p>
<h2>Input</h2><pre>${esc(t.input || "")}</pre>
${steps.length ? steps.map(stepHtml).join("\n") : "<p>This run had no steps (the whole skill was sent in one call).</p>"}
<h2>Final output</h2><pre>${esc(t.final_output || "(no output)")}</pre>
<div class="foot">Produced from <code>trace.json</code> by Skill Compiler. This file was generated on your computer at ${esc(when)}; nothing was sent anywhere and it needs no internet.
The trace is ${mock ? "MOCK" : "not marked as mock"}. Each attempt shows the format check (a script) and the model verifier's answer; a rejected attempt's checker note was sent back to the model with the retry.</div>
</main></body></html>`;
  }

  function fileName(trace) {
    const base = String((trace && (trace.run_id || trace.skill)) || "run").replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 60);
    return `report-${base}.html`;
  }

  /* Browser only: offer the report as a download. */
  function download(trace) {
    const blob = new Blob([buildReportHtml(trace)], { type: "text/html" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fileName(trace);
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return { buildReportHtml, fileName, esc, download };
});
