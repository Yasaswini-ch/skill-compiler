// Shared helpers for every page. No external requests: works from a local folder or a tiny Python server.
const REPO_URL = "https://github.com/Yasaswini-ch/skill-compiler";
const LABELS = ["skipped_step", "wrong_format", "lost_track", "merged_steps", "hallucinated_step", "ignored_constraint", "other"];

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("data-")) e.setAttribute(k, v);
    else if (v !== null && v !== undefined) e[k] = v;
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}

// Try web/data/<name> first, then web/mock/<name>. Falls back to the bundled .js copies so file:// works.
// Resolves to {data, source: "data"|"mock"}.
async function loadJSON(name) {
  for (const [folder, bundle] of [["data", "__DATA"], ["mock", "__MOCK"]]) {
    try {
      const r = await fetch(`${folder}/${name}`);
      if (r.ok) return { data: await r.json(), source: folder };
    } catch (e) { /* file:// or offline: use the bundle */ }
    const b = window[bundle] && window[bundle][name];
    if (b) return { data: b, source: folder };
  }
  throw new Error(`Could not load ${name} from web/data/ or web/mock/`);
}

function nav(current) {
  const pages = [["index.html", "Score"], ["museum.html", "Fail Museum"], ["trace.html", "Trace viewer"], ["lint.html", "Linter"], ["live.html", "Live"]];
  const h = el("header", { class: "top" }, el("span", { class: "brand" }, "Skill Compiler + Gemma Fail Museum"));
  for (const [href, label] of pages) h.append(el("a", { href, ...(href === current ? { "aria-current": "page" } : {}) }, label));
  h.append(el("a", { href: REPO_URL }, "GitHub"));
  const main = document.querySelector("main");
  if (main) main.id = "main";
  document.body.prepend(el("a", { class: "skip", href: "#main" }, "Skip to content"), h);
}

// Red banner shown whenever data is mock. message explains which data.
function mockBanner(show, message = "MOCK DATA - harness not connected. Do not use these numbers.") {
  let b = document.getElementById("mock-banner");
  if (!b) { b = el("div", { id: "mock-banner", class: "banner", role: "alert" }); document.body.prepend(b); }
  b.textContent = message;
  b.classList.toggle("show", !!show);
}

function labelTag(label) { return el("span", { class: "tag", "data-label": label || "other" }, label || "other"); }
function pill(kind, text) { return el("span", { class: `pill ${kind}` }, text || kind); }

const REDUCED_MOTION = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

// 38800 -> "38.8s", 501500 -> "8m 21.5s"
function fmtDuration(ms) {
  if (ms == null || isNaN(ms)) return "-";
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${(s % 60).toFixed(1)}s`;
}

// Count a number up from 0 once, unless the user prefers reduced motion. el shows `${n}${suffix}`.
function countUp(node, n, suffix = "", ms = 450) {
  if (REDUCED_MOTION || !isFinite(n)) { node.textContent = n + suffix; return; }
  let done = false;
  const finish = () => { done = true; node.textContent = n + suffix; };
  const t0 = performance.now();
  const tick = now => {
    if (done) return;
    const p = Math.min(1, (now - t0) / ms);
    if (p >= 1) return finish();
    node.textContent = Math.round(n * (1 - Math.pow(1 - p, 3))) + suffix;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  setTimeout(finish, ms + 150);   // always end on the real number, even if frames were skipped
}

let _replayToken = 0;
const _sleep = ms => new Promise(r => setTimeout(r, ms));

// Draw a trace.json into container. Handles missing optional fields (e.g. totals.cache_hits) and long notes.
// opts.replay adds a Replay button that plays the recorded run back; chips show the recorded latency, not replay time.
function renderTrace(trace, container, opts = {}) {
  _replayToken++;   // cancels any replay still running on a previous trace
  container.replaceChildren();
  const steps = trace.steps || [];
  const t = trace.totals || {};
  const n = s => steps.filter(x => x.status === s).length;
  const summary = steps.length
    ? `Ran ${steps.length} step${steps.length === 1 ? "" : "s"} in ${fmtDuration(t.latency_ms)}`
    : `One model call in ${fmtDuration(t.latency_ms)}`;
  const detail = steps.length ? `${n("pass")} passed first try · ${n("repaired")} repaired · ${n("fail")} failed` : "Plain mode: the whole skill went to the model at once.";
  const run = el("div", { class: "runline" }, el("span", { class: "summary" }, summary));
  const runsub = el("p", { class: "runsub" }, detail);
  container.append(run, runsub);

  const stats = [["mode", trace.mode || "?"], ["model calls", t.llm_calls ?? "-"], ["retries", t.retries ?? "-"]];
  if (t.cache_hits != null) stats.push(["cache hits", t.cache_hits]);
  container.append(el("div", { class: "totals" }, stats.map(([k, v]) => el("span", { class: "stat" }, k, el("b", {}, v)))));
  container.append(el("p", { class: "source" }, `skill ${trace.skill || "?"} · model ${trace.model || "?"} · run ${trace.run_id || "?"}`));

  const tl = el("div", { class: "timeline" });
  for (const s of steps) {
    const attempts = s.attempts || [];
    const body = el("div", {}, el("h3", {}, el("span", { class: "no" }, `STEP ${s.step_id}`), s.title || "", el("span", { class: "state" }, s.status === "pass" ? "passed" : s.status === "fail" ? "failed" : s.status)));
    attempts.forEach((a, i) => {
      const ok = a.format_ok && a.verified;
      if (i > 0) body.append(el("div", { class: "retry-arrow" }, "↳ checker feedback sent back, model tries again"));
      body.append(el("div", { class: "attempt " + (ok ? "ok" : "bad") },
        el("span", { class: "chip" }, `${ok ? "✓" : "✕"} attempt ${i + 1} · ${fmtDuration(a.latency_ms)}`),
        el("pre", {}, a.output ?? ""),
        a.checker_note && a.checker_note !== "ok" ? el("p", { class: ok ? "note fine" : "note" }, "checker: " + a.checker_note) : null));
    });
    tl.append(el("div", { class: `step ${s.status}` }, el("div", { class: "mark", "aria-hidden": "true" }), body));
  }
  container.append(tl);
  let final = null;
  if (trace.final_output) { final = el("div", {}, el("h2", {}, "Final output"), el("pre", {}, trace.final_output)); container.append(final); }

  if (opts.replay && steps.length) {
    const btn = el("button", { class: "ghost" }, "▶ Replay this run");
    btn.onclick = () => replayTrace(container, run, summary, btn, final);
    container.insertBefore(el("div", { class: "controls" }, btn, el("span", { class: "hint" }, "plays the recorded run back; durations shown are the real ones")), tl);
  }
}

async function replayTrace(container, run, summary, btn, final) {
  if (REDUCED_MOTION) return;   // nothing to animate: the full run is already on screen
  const token = ++_replayToken;
  const live = () => token === _replayToken;
  const stepEls = [...container.querySelectorAll(".step")];
  const hide = x => x.classList.add("pending");
  const show = x => { x.classList.remove("pending"); x.classList.add("reveal"); };
  btn.disabled = true;
  stepEls.forEach(st => { hide(st); st.querySelectorAll(".attempt, .retry-arrow").forEach(hide); });
  if (final) hide(final);
  run.querySelector(".summary").textContent = "Replaying...";
  for (const [si, st] of stepEls.entries()) {
    if (!live()) return;
    show(st);
    run.querySelector(".summary").textContent = `Replaying... step ${si + 1} of ${stepEls.length}`;
    const kids = [...st.querySelectorAll(".attempt, .retry-arrow")];
    for (const k of kids) {
      if (!live()) return;
      show(k);
      if (k.classList.contains("attempt")) { k.classList.add("running"); await _sleep(650); k.classList.remove("running"); if (!live()) return; }
      else await _sleep(250);
    }
    await _sleep(150);
  }
  if (!live()) return;
  if (final) show(final);
  run.querySelector(".summary").textContent = summary;   // settle on the real recorded time
  btn.disabled = false;
}

// Count failure labels from results.json tasks for one side ("plain" or "harness").
function labelCounts(results, side) {
  const c = {};
  for (const t of results.tasks || []) {
    const r = t[side];
    if (r && !r.passed) c[r.failure_label || "other"] = (c[r.failure_label || "other"] || 0) + 1;
  }
  return c;
}
