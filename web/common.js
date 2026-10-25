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
  document.body.prepend(h);
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

// Draw a trace.json into container. Handles missing optional fields (e.g. totals.cache_hits) and long notes.
function renderTrace(trace, container) {
  container.replaceChildren();
  const t = trace.totals || {};
  const stats = [["Mode", trace.mode || "?"], ["LLM calls", t.llm_calls ?? "-"], ["Latency", t.latency_ms != null ? (t.latency_ms / 1000).toFixed(1) + " s" : "-"], ["Retries", t.retries ?? "-"]];
  if (t.cache_hits != null) stats.push(["Cache hits", t.cache_hits]);
  container.append(el("div", { class: "totals" }, stats.map(([k, v]) => el("div", { class: "stat" }, el("span", { class: "hint" }, k), el("b", {}, v)))));
  container.append(el("p", { class: "hint" }, `Skill: ${trace.skill || "?"}  |  Model: ${trace.model || "?"}  |  Run: ${trace.run_id || "?"}`));
  if (!(trace.steps || []).length) {
    container.append(el("div", { class: "empty" }, trace.mode === "plain" ? "Plain mode: one call, no steps. The whole skill went to the model at once." : "This trace has no steps."));
  }
  const tl = el("div", { class: "timeline" });
  for (const s of trace.steps || []) {
    const attempts = s.attempts || [];
    const card = el("div", { class: `step ${s.status}` }, el("h3", {}, `Step ${s.step_id}: ${s.title || ""}`, pill(s.status), attempts.length > 1 ? el("span", { class: "hint" }, `${attempts.length} attempts`) : null));
    attempts.forEach((a, i) => {
      const ok = a.format_ok && a.verified;
      if (i > 0) card.append(el("div", { class: "retry-arrow" }, "↳ checker feedback sent back, model tries again"));
      card.append(el("div", { class: "attempt" + (ok ? "" : " bad") },
        el("div", { class: "meta" }, `Attempt ${i + 1}  |  format ${a.format_ok ? "ok" : "BAD"}  |  verified ${a.verified ? "yes" : "NO"}  |  ${a.latency_ms ?? "?"} ms`),
        el("pre", {}, a.output ?? ""),
        a.checker_note && a.checker_note !== "ok" ? el("div", { class: "hint" }, "Checker: " + a.checker_note) : null));
    });
    tl.append(card);
  }
  container.append(tl);
  if (trace.final_output) container.append(el("h2", {}, "Final output"), el("pre", {}, trace.final_output));
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
