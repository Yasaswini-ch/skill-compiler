/* X-ray renderer. Feed it the harness's events (or replay a recorded run) and it draws the steps lighting up.
   Needs web/xray-core.js (the logic) and the el() helper from common.js. */
(function () {
  "use strict";
  const X = window.XRayCore;
  const WORD = { pending: "queued", running: "running", pass: "passed", repaired: "repaired", fail: "failed" };
  const GLYPH = { pending: "○", running: "●", pass: "✓", repaired: "✓", fail: "✗" };
  const cardKey = s => (s.state === "pending" ? "pending" : s.state === "running" ? "running" : s.kind || "pass");

  function setText(node, text) { if (node.textContent !== text) node.textContent = text; }
  function setAttr(node, name, value) { const v = value == null ? "" : String(value); if (node.getAttribute(name) !== v) node.setAttribute(name, v); }

  class XRay {
    constructor(container, opts = {}) {
      this.container = container;
      this.opts = Object.assign({ live: false }, opts);
      this.state = X.initialState();
      this.cards = new Map();
      this.plan = new Map();
      this.timer = null;
      this.player = { events: [], i: 0, speed: 1, paused: false, t: null, onDone: null };
      this.build();
    }

    build() {
      this.bar = el("div", { class: "xr-bar", role: "status" });
      this.stats = {};
      for (const [key, label, kind] of [["attempts", "attempts", ""], ["calls", "model calls", ""], ["secs", "seconds", ""], ["retries", "retries", "retry"]]) {
        const b = el("b", {}, "0");
        this.stats[key] = b;
        this.bar.append(el("div", { class: "xr-stat", ...(kind ? { "data-kind": kind } : {}) }, b, el("span", {}, label)));
      }
      this.modeChip = el("span", { class: "xr-chip", hidden: "" });
      this.phase = el("span", { class: "xr-phase" });
      this.bar.append(this.modeChip, this.phase);
      this.err = el("p", { class: "xr-err", hidden: "" });
      this.planList = el("ol");
      this.planBox = el("aside", { class: "xr-plan", "aria-label": "Skill steps" }, el("h2", {}, "Skill steps"), this.planList);
      this.steps = el("section", { class: "xr-steps", "aria-label": "Run" });
      this.final = el("div", { class: "xr-final", hidden: "" });
      this.empty = el("div", { class: "xr-empty" }, "Nothing running yet.");
      this.grid = el("div", { class: "xr-grid" }, this.planBox, el("div", {}, this.steps, this.final));
      this.container.replaceChildren(el("div", { class: "xr" }, this.bar, this.err, this.empty, this.grid));
      this.grid.hidden = true;
    }

    reset() {
      this.stopTimer();
      this.state = X.initialState();
      this.cards.clear(); this.plan.clear();
      this.planList.replaceChildren(); this.steps.replaceChildren();
      this.render();
    }

    feed(event) {
      if (event && event.type === "run_start") { this.cards.clear(); this.plan.clear(); this.planList.replaceChildren(); this.steps.replaceChildren(); this.t0 = performance.now(); }
      this.state = X.reduce(this.state, event);
      this.render();
      if ((this.state.phase === "splitting" || this.state.phase === "running") && this.opts.live && !this.timer) this.startTimer();
      if (this.state.phase === "done" || this.state.phase === "error") this.stopTimer();
    }

    startTimer() { this.timer = setInterval(() => this.renderStats(), 200); }
    stopTimer() { if (this.timer) { clearInterval(this.timer); this.timer = null; } }

    renderStats() {
      const s = this.state;
      setText(this.stats.attempts, String(s.attempts));
      setText(this.stats.calls, s.calls == null ? "–" : String(s.calls));
      const secs = this.opts.live && s.phase !== "done" && s.phase !== "error" && this.t0 ? (performance.now() - this.t0) / 1000
        : (s.trace && s.trace.totals && s.trace.totals.latency_ms != null ? s.trace.totals.latency_ms / 1000 : s.recordedMs / 1000);
      setText(this.stats.secs, secs.toFixed(1));
      setText(this.stats.retries, String(s.retries));
    }

    render() {
      const s = this.state, sum = X.summary(s);
      this.renderStats();
      const idle = s.phase === "idle";
      this.empty.hidden = !idle; this.grid.hidden = idle || (!s.steps.length && s.phase !== "done");
      const label = { idle: "", splitting: "Splitting the skill into steps…", running: `Running step ${Math.min(sum.passed + sum.repaired + sum.failed + 1, sum.total)} of ${sum.total}`,
        done: `Done: ${sum.passed} passed first try, ${sum.repaired} repaired, ${sum.failed} failed`, error: "Stopped" }[s.phase];
      setText(this.phase, label || "");
      const chipText = s.route ? `${s.route.route} route` : (s.mode && s.mode !== "full" ? s.mode : "");
      this.modeChip.hidden = !chipText; setText(this.modeChip, chipText);
      if (s.route && s.route.reason) setAttr(this.modeChip, "title", s.route.reason);
      this.err.hidden = s.phase !== "error"; setText(this.err, s.error);

      for (const step of s.steps) {
        let li = this.plan.get(step.id), card = this.cards.get(step.id);
        if (!li) {
          li = el("li", {}, el("b", {}, `STEP ${step.id}`), el("span", {}, step.instruction || step.title));
          this.plan.set(step.id, li); this.planList.append(li);
        }
        setAttr(li, "data-state", step.state); setAttr(li, "data-kind", step.kind);
        if (!card) { card = this.makeCard(step); this.cards.set(step.id, card.root); card.root._parts = card; this.steps.append(card.root); }
        this.updateCard(this.cards.get(step.id), step);
      }
      if (s.phase === "done" && s.trace) this.renderFinal(s.trace, sum); else this.final.hidden = true;
    }

    makeCard(step) {
      const glyph = el("span", { class: "xr-glyph", "aria-hidden": "true" }), word = el("span", { class: "xr-word" });
      const attempts = el("div", { class: "xr-attempts" });
      const root = el("article", { class: "xr-card" }, el("div", { class: "xr-head" }, glyph, el("span", { class: "xr-no" }, `Step ${step.id}`),
        el("span", { class: "xr-title" }, step.title), word), attempts);
      return { root, glyph, word, attempts, rows: new Map() };
    }

    updateCard(root, step) {
      const p = root._parts, key = cardKey(step);
      setAttr(root, "data-state", step.state); setAttr(root, "data-kind", step.kind);
      setText(p.glyph, GLYPH[key]); setText(p.word, WORD[key]);
      for (const a of step.attempts) {
        let row = p.rows.get(a.n);
        if (!row) {
          row = { root: el("div", { class: "xr-attempt" }), retry: null, verdict: el("span", { class: "xr-verdict" }), lat: el("span"), model: el("span"),
                  out: el("pre", { class: "xr-out" }), note: el("p", { class: "xr-note" }), prev: "" };
          row.root.append(el("div", { class: "xr-meta" }, el("span", {}, `attempt ${a.n}`), row.verdict, row.lat, row.model), row.out, row.note);
          if (a.n > 1) { row.retry = el("p", { class: "xr-retry" }, "↳ checker feedback sent back, trying again"); row.root.prepend(row.retry); }
          p.rows.set(a.n, row); p.attempts.append(row.root);
        }
        setAttr(row.root, "data-chip", a.chip);
        setText(row.verdict, a.chip === "running" ? "running…" : a.chip === "done" ? "passed" : "rejected");
        setText(row.lat, a.latencyMs ? `${(a.latencyMs / 1000).toFixed(1)} s` : "");
        setText(row.model, a.model ? `on ${a.model}` : "");
        setText(row.out, a.chip === "running" ? "" : (a.output || "(no output)"));
        setText(row.note, a.chip === "error" && a.note ? `Checker: ${a.note}` : "");
        row.note.hidden = !(a.chip === "error" && a.note);
        if (row.prev !== "error" && a.chip === "error") { row.root.classList.add("flash"); setTimeout(() => row.root.classList.remove("flash"), 1000); }
        row.prev = a.chip;
      }
    }

    renderFinal(trace, sum) {
      this.final.hidden = false;
      const shown = (trace.final_output || "").trim() || "(no output)";
      this.final.replaceChildren(el("h2", {}, "Final output"),
        el("p", { class: "xr-sum" }, `${sum.passed} passed first try · ${sum.repaired} repaired · ${sum.failed} failed · ${trace.totals ? trace.totals.llm_calls : "?"} model calls`),
        el("pre", {}, shown));
    }

    /* ---- replay ---- */
    play(events, opts = {}) {
      this.stopPlayback();
      this.opts.live = false;
      Object.assign(this.player, { events, i: 0, speed: opts.speed || this.player.speed || 1, paused: false, onDone: opts.onDone || null });
      this.reset();
      this.tick();
    }
    tick() {
      const pl = this.player;
      if (pl.paused) return;
      if (pl.i >= pl.events.length) { if (pl.onDone) pl.onDone(); return; }
      const e = pl.events[pl.i], wait = pl.i === 0 ? 0 : X.delayFor(e, pl.speed);
      pl.t = setTimeout(() => { this.feed(e); pl.i++; this.tick(); }, wait);
    }
    pause() { this.player.paused = true; clearTimeout(this.player.t); }
    resume() { if (this.player.paused) { this.player.paused = false; this.tick(); } }
    setSpeed(x) { this.player.speed = x; }
    stopPlayback() { clearTimeout(this.player.t); this.player.paused = true; }
    showAll(events) { this.stopPlayback(); this.opts.live = false; this.reset(); for (const e of events) this.feed(e); }

    /* ---- a live NDJSON stream (a harness run in progress) ---- */
    async follow(url, init) {
      this.stopPlayback(); this.reset(); this.opts.live = true;
      this.abort = new AbortController();
      const res = await fetch(url, Object.assign({ signal: this.abort.signal }, init || {}));
      if (!res.ok) { let msg = `The server answered ${res.status}.`; try { msg = (await res.json()).error || msg; } catch (_) { /* not JSON */ } throw new Error(msg); }
      const reader = res.body.getReader(), dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
          if (line) this.feed(JSON.parse(line));
        }
      }
      this.stopTimer();
    }
    cancel() { if (this.abort) this.abort.abort(); this.stopTimer(); }
  }

  /* The plain column: one answer and the checks it failed. result = {output, passed: true|false|null, failed_checks: [{id, label, reason}], note} */
  XRay.renderPlain = function (container, result) {
    const pass = result.passed;
    const word = pass === true ? "passed all checks" : pass === false ? "broke a rule" : "UNVERIFIED: nobody scored this";
    const box = el("div", { class: "xp", "data-pass": String(pass) }, el("h2", {}, "Plain Gemma · one call, no steps"), el("span", { class: "xp-stamp" }, word),
      el("pre", {}, (result.output || "").trim() || "(no output)"));
    const failed = result.failed_checks || [];
    if (failed.length) {
      const ul = el("ul");
      for (const f of failed) ul.append(el("li", {}, f.label || f.id || String(f), f.reason ? el("span", {}, ` — ${f.reason}`) : ""));
      box.append(ul);
    }
    if (result.note) box.append(el("p", { class: "hint" }, result.note));
    container.replaceChildren(box);
  };

  window.XRay = XRay;
})();
